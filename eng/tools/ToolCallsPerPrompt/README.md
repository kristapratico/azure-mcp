# Tool Calls per Prompt for Azure MCP

The Tool Calls per Prompt tool validates that AI models correctly invoke Azure MCP tools with appropriate parameters when responding to user queries.

## Overview

This tool consists of two main components:

1. **Test Data Generator** (`get_latest_e2e.py`) - Converts end-to-end test prompts from markdown format into structured JSONL test data
2. **Runner** (`run.py`) - Executes tool calls against the Azure MCP server and generates reports.

## Prerequisites

- Python 3.10 or higher
- Node.js and npm (for Azure MCP server)
- Azure credentials configured
- Required environment variables:
  - `AZURE_OPENAI_ENDPOINT`
  - `AZURE_OPENAI_API_KEY`

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

## Usage

The script is run against live resources. Ensure you've deployed the resources you want to test against and have a .testsettings.json file configured with your Azure environment details under the service area you want to test.

### Running via PowerShell Script (Recommended)

Use the provided PowerShell script for automated execution:

```powershell
# Run all service areas
./Test-ToolCallsPerPrompt.ps1

# Run specific service areas
./Test-ToolCallsPerPrompt.ps1 -Areas Storage,Cosmos
```

### Manual Execution

#### Step 1: Generate Test Data

```bash
# Generate test data for all services
python get_latest_e2e.py

# Generate test data for specific services
python get_latest_e2e.py --service cosmos,storage --output data.jsonl
```

#### Step 2: Run

```bash
python run.py
```

## Configuration Files

### Service Mappings (`service_mappings.json`)
Maps markdown section headers to standardized service names:
```json
{
  "Azure Cosmos DB": "cosmos",
  "Azure Storage": "storage",
  "Azure Key Vault": "keyvault"
}
```

### Variable Mappings (`variable_mappings.json`)
Defines placeholder replacements for test data:
```json
{
  "cosmos": {
    "<account_name>": "ResourceBaseName",
    "<database_name>": "ToDoList",
    "<container_name>": "Items"
  }
}
```

## Test Data Format

The tool generates JSONL test data with the following structure:
```json
{
  "query": "List all cosmosdb accounts in my subscription",
  "expected_tool_calls": ["cosmos", "cosmos_account_list"],
  "service_area": "cosmos"
}
```

## Metrics

The engine scores each test case based on three criteria:

- **Tool Selection (50%)**: Correct tool and command were called
- **Parameter Validation (30%)**: Required parameters were provided correctly
- **Call Count (20%)**: Expected number of tool calls were made

**Overall Score Threshold**: 0.8 (configurable via `SCORE_THRESHOLD`)

## Output

### Console Output
- Formatted table showing test results
- Overall metrics and pass/fail status
- Detailed failure reasons for debugging

### Results File
Results are saved to `.log/result.json` containing:
- Individual test case results
- Aggregate metrics
- Token usage statistics
- Tool call traces


## Contributing

When adding new test cases:
1. Add prompts to `/e2eTests/e2eTestPrompts.md`
2. Update service mappings if needed
3. Configure variable mappings for new placeholders
4. Test with the powershell script or manually as described above
