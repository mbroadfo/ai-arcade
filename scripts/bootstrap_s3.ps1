[CmdletBinding()]
param(
    [string]$StackName = "ai-arcade-backup",
    [string]$Region = "us-west-2",
    [string]$Profile = "default",
    [string]$BucketName = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Template = Join-Path $RepoRoot "infra/cloudformation/backup-bucket.yaml"

if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    throw "AWS CLI was not found in PATH. Install AWS CLI v2 and configure credentials first."
}

$args = @(
    "cloudformation", "deploy",
    "--template-file", $Template,
    "--stack-name", $StackName,
    "--region", $Region,
    "--profile", $Profile,
    "--no-fail-on-empty-changeset",
    "--parameter-overrides", "BucketName=$BucketName"
)

Write-Host "Deploying private AI Arcade backup bucket..."
& aws @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$bucket = & aws cloudformation describe-stacks `
    --stack-name $StackName `
    --region $Region `
    --profile $Profile `
    --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue | [0]" `
    --output text

Write-Host ""
Write-Host "Backup bucket: $bucket"
Write-Host "Update config/local.yaml with this bucket name."
