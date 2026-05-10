## Connecting Antigravity to Codespaces

We will use [Google Antigravity](https://antigravity.google/) as the AI assistant and Codepaces as the environment.

In this section I will show how to connect Antigravity to Codespaces.

Step 1: Install GitHub CLI
- Download from https://github.com/cli/cli/releases
- Windows installation steps
    - open powershell and install [winget](https://learn.microsoft.com/en-us/windows/package-manager/winget/) 
```
winget install --id GitHub.cli
choco install gh
```

Step 2: Authenticate

```
# Authenticate with Github using ssh
gh auth login
# select: SSH protcol and your existing SSH key for Github
# Follow the remaining prompts

# authenticate for codespaces
gh auth refresh -h github.com -s codespace
```

Step 3: Create and Use Codespace
```
gh codespace create
# Note the ID that's generated (e.g., glorious-space-chainsaw-rpxj65wq969fp5wq)
```

Step 4: Connect via SSH
```
gh codespace ssh -c glorious-space-chainsaw-rpxj65wq969fp5wq
```
Next, get the SSH config:
```
gh codespace ssh --config -c glorious-space-chainsaw-rpxj65wq969fp5wq
```

add the output to ~/.ssh/config

Step 5: Use with Antigravity
- Connect to codespace using Antigravity's SSH remote node
- Open the project folder in /workspaces/

Step 6: Stop Codespaces when done
```
gh cs stop -c glorious-space-chainsaw-rpxj65wq969fp5wq
```