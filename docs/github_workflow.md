# GitHub Workflow

This project should be published module by module. Each module must be a small,
working prototype that has been tested locally before it is pushed.

## Module Release Rule

For every module:

1. Implement only the current module scope.
2. Run the relevant tests.
3. Run a manual CLI smoke test.
4. Commit the working prototype.
5. Push to GitHub.
6. Optionally tag the module milestone.

Do not batch unrelated future modules into the same commit.

## Local Checklist

Before committing a module:

```bash
python3 -m unittest
python3 main.py --help
```

For Module 1:

```bash
tmpdir=$(mktemp -d)
python3 main.py init-project --name autonomy_blockchain_paper --projects-root "$tmpdir/projects"
python3 main.py status --project autonomy_blockchain_paper --projects-root "$tmpdir/projects"
```

## Suggested Commit Names

```text
module-1 project manager
module-2 dataset manager
module-3 pdf processor
module-3.5 bibliography manager
module-4 index builder
module-5 query engine
module-6 outline generator
```

## Suggested Tags

```text
module-1-project-manager
module-2-dataset-manager
module-3-pdf-processor
module-3.5-bibliography-manager
module-4-index-builder
module-5-query-engine
module-6-outline-generator
```

## First GitHub Publish

If Git is not initialized:

```bash
git init
git add .
git commit -m "module-1 project manager"
```

Create an empty repository on GitHub, then connect it:

```bash
git branch -M main
git remote add origin git@github.com:<your-user>/<your-repo>.git
git push -u origin main
```

If you prefer the GitHub CLI, install and authenticate `gh` first:

```bash
gh auth login
gh repo create <your-repo> --private --source=. --remote=origin --push
```

Use `--public` instead of `--private` only when the repository is ready to be
public.

## After Each Module

```bash
python3 -m unittest
git status --short
git add <changed-files>
git commit -m "module-N short description"
git push
```

Optional tag:

```bash
git tag module-N-short-name
git push origin module-N-short-name
```

## GitHub Actions

The repository includes `.github/workflows/tests.yml`, which runs:

```bash
python -m unittest
```

on every push and pull request.
