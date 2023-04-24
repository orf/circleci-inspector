import os

import click
from dotenv import load_dotenv
import asyncio
import httpx
from tqdm import tqdm as sync_tqdm
from aiostream import stream, pipe
import orjson
import tenacity


async def paginate(client: httpx.AsyncClient, request: httpx.Request, *, limit: int):
    while True:
        response = await client.send(request)
        json_content = response.json()
        for item in json_content["items"]:
            yield item
            limit -= 1
            if limit == 0:
                return
        if not json_content["next_page_token"]:
            return
        request.url = request.url.copy_merge_params(
            {"page-token": json_content["next_page_token"]}
        )



class RetryingClient(httpx.AsyncClient):
    @tenacity.retry(stop=tenacity.stop_after_attempt(3))
    async def send(self, *args, **kwargs) -> httpx.Response:
        response = await super().send(*args, **kwargs)
        response.raise_for_status()
        return response


@click.command()
@click.argument("org", type=str)
@click.argument("repo", type=str)
@click.argument("output", type=click.File("wb"))
@click.option("--limit", type=int, default=1000)
def main(org, repo, output, limit):
    asyncio.run(_main(org, repo, output, limit))


async def _main(org, repo, output, limit):
    load_dotenv()
    circle_base_url = "https://circleci.com/api/v2"
    circle_v1_base_url = "https://circleci.com/api/v1.1"
    headers = {"Accept": "application/json", "Circle-Token": os.environ["CIRCLE_TOKEN"]}

    transport = httpx.AsyncHTTPTransport(retries=4, http2=True, http1=False)

    async with RetryingClient(headers=headers, transport=transport) as client:
        request = client.build_request(
            "GET",
            f"{circle_base_url}/project/github/{org}/{repo}/pipeline",
            headers=headers,
        )
        pipelines = stream.iterate(paginate(client, request, limit=limit))

        async def get_workflows(pipeline: dict):
            pipeline_id = pipeline["id"]
            resp = await client.get(
                f"{circle_base_url}/pipeline/{pipeline_id}/workflow"
            )
            for item in resp.json()["items"]:
                yield item

        async def get_jobs(workflow: dict):
            workflow_id = workflow["id"]
            workflow_data = paginate(
                client,
                client.build_request(
                    "GET", f"{circle_base_url}/workflow/{workflow_id}/job"
                ),
                limit=-1,
            )
            async for item in workflow_data:
                yield item

        async def get_job_details(job: dict):
            if "job_number" not in job:
                return
            job_number = job["job_number"]
            job_data = await client.get(
                f"{circle_v1_base_url}/project/github/{org}/{repo}/{job_number}"
            )
            job_data = job_data.json()
            lifecycle = job_data["lifecycle"]
            total = job_data["build_time_millis"]
            workflow_job_name = job_data["workflows"]["job_name"]
            workflow_job_id = job_data["workflows"]["job_id"]
            build_url = job_data["build_url"]

            for step in job_data["steps"]:
                for action in step["actions"]:
                    step_total = action["run_time_millis"]
                    status = action["status"]
                    name = action["name"]
                    yield {
                        "lifecycle": lifecycle,
                        "total": total,
                        "job_name": workflow_job_name,
                        "action_name": name,
                        "step_total": step_total,
                        "status": status,
                        "workflow_job_id": workflow_job_id,
                        "build_url": build_url,
                    }

        with sync_tqdm(
            desc="pipelines", position=0, total=limit
        ) as pipelines_pb, sync_tqdm(
            desc="workflows", position=1
        ) as workflow_pb, sync_tqdm(
            desc="jobs", position=2
        ) as jobs_pb:
            ys = (
                pipelines
                | pipe.action(lambda v: pipelines_pb.update())
                | pipe.flatmap(get_workflows)
                | pipe.action(lambda v: workflow_pb.update())
                | pipe.flatmap(get_jobs)
                | pipe.action(lambda v: jobs_pb.update())
                | pipe.flatmap(get_job_details)
            )

            async with ys.stream() as streamer:
                async for z in streamer:
                    if z is not None:
                        output.write(orjson.dumps(z))
                        output.write(b"\n")
