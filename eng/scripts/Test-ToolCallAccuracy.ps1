#!/usr/bin/env pwsh
#Requires -Version 7

<#
.SYNOPSIS
    Runs Azure MCP tool call accuracy with the specified test type and areas.

.DESCRIPTION
    This script installs requirements and runs the ToolCallAccuracy tool consisting of:
    1. get_latest_e2e.py - generates test data
    2. run.py - executes tool call accuracy
    
    The script only runs if TF_BUILD environment variable is set to true (CI environment).

.PARAMETER TestType
    The type of tests to run. Valid values: 'Live', 'Unit', 'All'

.PARAMETER Areas
    Array of specific areas to test (e.g., 'Storage', 'KeyVault')

.EXAMPLE
    ./Test-ToolCallAccuracy.ps1 -TestType Live -Areas Storage,KeyVault
#>

[CmdletBinding()]
param(
    [ValidateSet('Live', 'Unit', 'All')]
    [string] $TestType = 'Live',
    [string[]] $Areas
)

$ErrorActionPreference = 'Stop'

Write-Host "Running Azure MCP tool call accuracy in CI environment" -ForegroundColor Green
Write-Host "TestType: $TestType" -ForegroundColor Cyan
if ($Areas) {
    Write-Host "Areas: $($Areas -join ', ')" -ForegroundColor Cyan
} else {
    Write-Host "Areas: All areas" -ForegroundColor Cyan
}

# Get the repository root and ToolCallAccuracy directory
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ToolCallDir = Join-Path $RepoRoot "eng/tools/ToolCallAccuracy"

if (-not (Test-Path $ToolCallDir)) {
    Write-Error "ToolCallAccuracy directory not found: $ToolCallDir"
    exit 1
}

Write-Host "Repository Root: $RepoRoot" -ForegroundColor Yellow
Write-Host "ToolCallAccuracy Directory: $ToolCallDir" -ForegroundColor Yellow
Write-Host "Current working directory before change: $(Get-Location)" -ForegroundColor Cyan

# Change to ToolCallAccuracy directory
Push-Location $ToolCallDir
Write-Host "Current working directory after change: $(Get-Location)" -ForegroundColor Cyan
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
    Write-Host "Installing ToolCallAccuracy requirements..." -ForegroundColor Yellow
    if (Test-Path "requirements.txt") {
        python -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to install requirements from requirements.txt"
            exit $LASTEXITCODE
        }
    } else {
        Write-Warning "requirements.txt not found, exiting..."
        exit $LASTEXITCODE
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

    # Step 2: Run run.py to execute ToolCallAccuracy (no arguments needed)
    Write-Host "Step 2: Running ToolCallAccuracy with run.py..." -ForegroundColor Yellow
    Write-Host "About to run Python from directory: $(Get-Location)" -ForegroundColor Cyan
    
    if (Test-Path "run.py") {
        Write-Host "Running: python run.py" -ForegroundColor Cyan
        python run.py
        $toolCallExitCode = $LASTEXITCODE
        
        if ($toolCallExitCode -eq 0) {
            Write-Host "ToolCallAccuracy completed successfully" -ForegroundColor Green
        } else {
            Write-Error "ToolCallAccuracy failed with exit code $toolCallExitCode"
        }
        
        # Check for ToolCallAccuracy results
        $resultsFile = Join-Path $ToolCallDir ".log/result.json"
        if (Test-Path $resultsFile) {
            Write-Host "ToolCallAccuracy results saved to: $resultsFile" -ForegroundColor Green

            # If in Azure DevOps, attach the results file
            if ($env:TF_BUILD -eq 'true') {
                Write-Host "##vso[task.addattachment type=Distributedtask.Core.Summary;name=ToolCallAccuracy Results;]$resultsFile"
            }
        } else {
            Write-Warning "ToolCallAccuracy results file not found at: $resultsFile"
        }
        
        exit $toolCallExitCode
    } else {
        Write-Error "run.py not found in $ToolCallDir"
        exit 1
    }

} catch {
    Write-Error "An error occurred during ToolCallAccuracy execution: $($_.Exception.Message)"
    Write-Host "Stack trace: $($_.Exception.StackTrace)" -ForegroundColor Red
    exit 1
} finally {
    Pop-Location
}
