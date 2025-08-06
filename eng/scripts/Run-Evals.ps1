#!/usr/bin/env pwsh
#Requires -Version 7

<#
.SYNOPSIS
    Runs Azure MCP evaluations with the specified test type and areas.

.DESCRIPTION
    This script installs requirements and runs the evaluation pipeline consisting of:
    1. get_latest_e2e.py - generates test data
    2. run.py - executes evaluations
    
    The script only runs if TF_BUILD environment variable is set to true (CI environment).

.PARAMETER TestType
    The type of tests to run. Valid values: 'Live', 'Unit', 'All'

.PARAMETER Areas
    Array of specific areas to test (e.g., 'Storage', 'KeyVault')

.EXAMPLE
    ./Run-Evals.ps1 -TestType Live -Areas Storage,KeyVault
#>

[CmdletBinding()]
param(
    [ValidateSet('Live', 'Unit', 'All')]
    [string] $TestType = 'Live',
    [string[]] $Areas
)

$ErrorActionPreference = 'Stop'

# Only run in CI environment
if ($env:TF_BUILD -ne 'true') {
    Write-Warning "This script only runs in CI environment (TF_BUILD must be 'true'). Current TF_BUILD: '$env:TF_BUILD'"
    exit 0
}

Write-Host "Running Azure MCP Evaluations in CI environment" -ForegroundColor Green
Write-Host "TestType: $TestType" -ForegroundColor Cyan
if ($Areas) {
    Write-Host "Areas: $($Areas -join ', ')" -ForegroundColor Cyan
} else {
    Write-Host "Areas: All areas" -ForegroundColor Cyan
}

# Get the repository root and evals directory
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$EvalsDir = Join-Path $RepoRoot "core/tests/evals"

if (-not (Test-Path $EvalsDir)) {
    Write-Error "Evaluations directory not found: $EvalsDir"
    exit 1
}

Write-Host "Repository Root: $RepoRoot" -ForegroundColor Yellow
Write-Host "Evaluations Directory: $EvalsDir" -ForegroundColor Yellow

# Change to evals directory
Push-Location $EvalsDir
try {
    # Check if Python is available
    try {
        $pythonVersion = python --version 2>&1
        Write-Host "Python version: $pythonVersion" -ForegroundColor Green
    } catch {
        Write-Error "Python is not installed or not in PATH. Please install Python 3.10+ first."
        exit 1
    }

    # Check if pip is available
    try {
        $pipVersion = python -m pip --version 2>&1
        Write-Host "Pip version: $pipVersion" -ForegroundColor Green
    } catch {
        Write-Error "Pip is not available. Please ensure pip is installed with Python."
        exit 1
    }

    # Install/upgrade pip and basic packages
    Write-Host "Setting up Python environment..." -ForegroundColor Yellow
    python -m pip install --upgrade pip setuptools wheel
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to upgrade pip and basic packages"
        exit $LASTEXITCODE
    }

    # Install requirements
    Write-Host "Installing evaluation requirements..." -ForegroundColor Yellow
    if (Test-Path "requirements.txt") {
        python -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to install requirements from requirements.txt"
            exit $LASTEXITCODE
        }
    } else {
        Write-Warning "requirements.txt not found, installing core packages directly"
        python -m pip install azure-ai-evaluation azure-identity python-dotenv mcp openai tabulate tiktoken
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to install core packages"
            exit $LASTEXITCODE
        }
    }

    Write-Host "Requirements installed successfully" -ForegroundColor Green

    # Prepare arguments for get_latest_e2e.py
    $getE2EArgs = @()
    
    # Add Areas as service filter if specified
    if ($Areas -and $Areas.Count -gt 0) {
        # Convert Areas to lowercase service names for get_latest_e2e.py
        $serviceNames = $Areas | ForEach-Object { $_.ToLower() }
        $getE2EArgs += "--service", ($serviceNames -join ",")
    }

    # Step 1: Run get_latest_e2e.py to generate test data
    Write-Host "Step 1: Generating test data with get_latest_e2e.py..." -ForegroundColor Yellow
    
    if (Test-Path "get_latest_e2e.py") {
        if ($getE2EArgs.Count -gt 0) {
            Write-Host "Running: python get_latest_e2e.py $($getE2EArgs -join ' ')" -ForegroundColor Cyan
            python get_latest_e2e.py @getE2EArgs
        } else {
            Write-Host "Running: python get_latest_e2e.py" -ForegroundColor Cyan
            python get_latest_e2e.py
        }
        
        if ($LASTEXITCODE -ne 0) {
            Write-Error "get_latest_e2e.py failed with exit code $LASTEXITCODE"
            exit $LASTEXITCODE
        }
        Write-Host "Test data generation completed successfully" -ForegroundColor Green
    } else {
        Write-Warning "get_latest_e2e.py not found, skipping test data generation"
    }

    # Step 2: Run run.py to execute evaluations (no arguments needed)
    Write-Host "Step 2: Running evaluations with run.py..." -ForegroundColor Yellow
    
    if (Test-Path "run.py") {
        Write-Host "Running: python run.py" -ForegroundColor Cyan
        python run.py
        $evalExitCode = $LASTEXITCODE
        
        if ($evalExitCode -eq 0) {
            Write-Host "Evaluations completed successfully" -ForegroundColor Green
        } else {
            Write-Error "Evaluations failed with exit code $evalExitCode"
        }
        
        # Check for evaluation results
        $resultsFile = Join-Path $EvalsDir ".log/evaluation_result.json"
        if (Test-Path $resultsFile) {
            Write-Host "Evaluation results saved to: $resultsFile" -ForegroundColor Green
            
            # If in Azure DevOps, attach the results file
            if ($env:TF_BUILD -eq 'true') {
                Write-Host "##vso[task.addattachment type=Distributedtask.Core.Summary;name=Evaluation Results;]$resultsFile"
            }
        } else {
            Write-Warning "Evaluation results file not found at: $resultsFile"
        }
        
        exit $evalExitCode
    } else {
        Write-Error "run.py not found in $EvalsDir"
        exit 1
    }

} catch {
    Write-Error "An error occurred during evaluation execution: $($_.Exception.Message)"
    Write-Host "Stack trace: $($_.Exception.StackTrace)" -ForegroundColor Red
    exit 1
} finally {
    Pop-Location
}
