# Setting Up as GitHub Template Repository

## Step 1: Create the repo

```bash
# Option A: Create from this template on GitHub
# Click "Use this template" on https://github.com/technomaton/edpa

# Option B: CLI
gh repo create my-org/my-project --template technomaton/edpa-template --private
cd my-project
```

## Step 2: Configure your project

```bash
cp config/capacity.yaml.tmpl config/capacity.yaml
cp config/cw_heuristics.yaml.tmpl config/cw_heuristics.yaml
cp config/project.yaml.tmpl config/project.yaml
```

Edit `config/capacity.yaml` with your team members.
Edit `config/project.yaml` with your project name and metadata.

Or use Claude Code:
```
Set up EDPA governance for My Project
```

## Step 3: Configure GitHub Projects

See [docs/github-setup.md](docs/github-setup.md) for custom field definitions.

```bash
# Create project
gh project create --title "My Project Governance" --owner @me

# Add custom fields via GraphQL
PROJECT_ID=$(gh project list --owner @me --format json | jq -r '.projects[0].id')

gh project field-create $PROJECT_ID --name "Issue Type" --data-type "SINGLE_SELECT" \
  --single-select-options "Initiative,Epic,Feature,Story,Task,Bug"
gh project field-create $PROJECT_ID --name "Job Size" --data-type "NUMBER"
gh project field-create $PROJECT_ID --name "Business Value" --data-type "NUMBER"
gh project field-create $PROJECT_ID --name "Time Criticality" --data-type "NUMBER"
gh project field-create $PROJECT_ID --name "Risk Reduction" --data-type "NUMBER"
gh project field-create $PROJECT_ID --name "WSJF Score" --data-type "NUMBER"
```

## Step 4: Verify

```bash
# Test branch naming check
git checkout -b feature/S-001-test-story
echo "test" > test.txt
git add . && git commit -m "test: verify branch naming"
git push origin feature/S-001-test-story
gh pr create --title "S-001: Test story" --body "Closes #1"
# CI should pass

# Test EDPA engine
python scripts/edpa_engine.py --demo
```

## Step 5: Mark as template (optional)

If you want others to use your configured repo as a template:
1. Go to repo **Settings** → scroll to **Template repository**
2. Check **"Template repository"**
