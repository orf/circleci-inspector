# CircleCI inspector

This is a hacky and quick tool to dump CircleCI build information for all builds in a project.

```shell
$ dump-circleci "org-name" "repo-name" --limit=5000 pipelines.jsonl
pipelines:   1%|████                       | 43/5000 [00:09<27:14,  3.03it/s]
workflows: 42it [00:09,  2.60it/s]
jobs: 3017it [00:09, 382.49it/s]
```

For the first 5000 (`--limit`) pipelines in a given repo, the tool will:
1. Fetch all workflows
2. For each workflow, fetch all jobs
3. For each job, fetch detailed breakdowns and output them to the given file (or stdout)

```shell
$ head -n2 pipelines.jsonl | jq
{
  "lifecycle": "finished",
  "total": 93169,
  "workflow_job_name": "some_name",
  "step_total": 15724,
  "status": "success",
  "workflow_job_id": "UUID",
  "build_url": "https://circleci.com/..."
}
{
  "lifecycle": "finished",
  "total": 44917,
  "workflow_job_name": "some_other_name",
  "step_total": 1771,
  "status": "success",
  "workflow_job_id": "UUID",
  "build_url": "https://circleci.com/..."
}
```

## Install

```shell
$ pipx install git+https://github.com/orf/circleci-inspector.git
$ dump-circleci --version
```

For development, clone and run:

```shell
$ poetry install
```
