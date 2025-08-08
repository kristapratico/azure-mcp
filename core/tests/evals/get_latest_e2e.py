#!/usr/bin/env python3
import re
import os
import json
import argparse
from collections import defaultdict
import dotenv

dotenv.load_dotenv()


def load_config_from_json(filename):
    """Generic function to load a JSON configuration file
    
    Args:
        filename (str): Name of the JSON file (e.g., "service_mappings.json")
        
    Returns:
        dict: The configuration data, or empty dict if error
    """
    try:
        config_path = os.path.join(os.path.dirname(__file__), filename)
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"⚠️  WARNING: Error loading {filename}: {e}")
        return {}


def load_test_settings_from_file(test_settings_path=".testsettings.json", service_name=None):
    """
    Load environment values from a local .testsettings.json file.
    
    Args:
        test_settings_path (str): Path to the .testsettings.json file
        service_name (str): Optional service name to look for service-specific test settings
        
    Returns:
        dict: Dictionary containing the test settings, or empty dict if file not found
    """
    try:
        # If a service name is provided, look for service-specific test settings first
        if service_name:
            # Find the azure-mcp root directory
            current_dir = os.getcwd()
            azure_mcp_root = None
            
            # Search upwards for azure-mcp directory
            while current_dir != "/":
                if os.path.basename(current_dir) == "azure-mcp" or os.path.exists(os.path.join(current_dir, "areas")):
                    azure_mcp_root = current_dir
                    break
                current_dir = os.path.dirname(current_dir)
            
            if azure_mcp_root:
                service_test_settings = os.path.join(azure_mcp_root, "areas", service_name, "tests", ".testsettings.json")
                if os.path.exists(service_test_settings):
                    with open(service_test_settings, 'r', encoding='utf-8') as f:
                        settings = json.load(f)
                        print(f"✅ Loaded service-specific test settings from: {service_test_settings}")
                        return settings
                else:
                    print(f"⚠️  Service-specific test settings not found at: {service_test_settings}")

        return {}
        
    except (json.JSONDecodeError, FileNotFoundError, KeyError) as e:
        print(f"⚠️  WARNING: Error reading .testsettings.json: {e}.")
        return {}


def get_env(key, test_settings=None):
    """
    Get environment value from test settings or fall back to environment variables.
    
    Args:
        key (str): The key to look up (e.g., 'ResourceBaseName', 'TenantId')
        test_settings (dict): Optional test settings dictionary
        
    Returns:
        str: The environment value
    """
    if test_settings and key in test_settings:
        return test_settings[key]
    
    # Fallback to environment variable
    return os.environ.get(key)


def build_variable_mappings(service, test_settings):
    """Build variable mappings with the provided test settings"""
    # Load the template mappings from JSON
    variable_mapping_templates = load_config_from_json("variable_mappings.json")
    
    # Get the template for this service, or empty dict if not found
    service_template = variable_mapping_templates.get(service, {})
    
    # Build the actual mappings by resolving template values
    resolved_mappings = {}
    for placeholder, template_value in service_template.items():
        if isinstance(template_value, str):
            # Check if this is a reference to a test setting key
            if template_value in ["ResourceBaseName", "TenantId", "SubscriptionId", 
                                "TenantName", "SubscriptionName", "ResourceGroupName"]:
                resolved_value = get_env(template_value, test_settings)
            elif "{" in template_value and "}" in template_value:
                # Handle template strings like "/subscriptions/{SubscriptionId}/..."
                resolved_value = template_value.format(
                    SubscriptionId=get_env("SubscriptionId", test_settings),
                    ResourceGroupName=get_env("ResourceGroupName", test_settings)
                )
            else:
                # Use the literal value
                resolved_value = template_value
        else:
            # For non-string values, use as-is
            resolved_value = template_value
            
        resolved_mappings[placeholder] = resolved_value
    
    return resolved_mappings


def read_local_markdown_file(file_path):
    """Read a markdown file from local filesystem"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: Markdown file not found at: {file_path}")
        return None
    except Exception as e:
        print(f"Error reading the markdown file: {e}")
        return None


def parse_markdown_and_convert_to_jsonl(markdown_content, filter_service_names=None):
    """Parse the markdown content and convert it to JSONL format
    
    Args:
        markdown_content: The markdown content to parse
        filter_service_names: List of standardized service names (e.g., ['aks', 'cosmos']) to filter by
    """
    # Load service header mapping
    service_header_mapping = load_config_from_json("service_mappings.json")
    
    # Split the markdown content by sections (## headers)
    sections = re.split(r'##\s+', markdown_content)
    
    # Skip the first section as it's the intro before any ## headers
    sections = sections[1:]
    
    results = []
    
    # Process each section
    for section in sections:
        if not section.strip():
            continue
        
        # Extract section title and content
        lines = section.strip().split('\n')
        section_title = lines[0].strip() if lines else ""
        
        # Convert markdown H2 header to standardized service name
        standardized_service_name = service_header_mapping.get(section_title)
        
        # If filter_service_names is specified, only process sections that match the standardized names
        if filter_service_names and standardized_service_name not in filter_service_names:
            continue
        
        # If we don't have a mapping for this service, skip it
        if not standardized_service_name:
            continue
        
        # Find the table content (lines between |:-----|:------|)
        table_start = False
        table_data = []
        
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
                
            # Skip table header line (with colons and dashes)
            if re.match(r'\|:?-+:?\|:?-+:?\|', line):
                table_start = True
                continue
            
            # If we've found the table and this is a table row
            if table_start and line.startswith('|') and line.endswith('|'):
                table_data.append(line)
        
        # Process each table row
        for row in table_data:
            # Split the row by | and remove the empty first and last elements
            cells = [cell.strip() for cell in row.split('|')[1:-1]]
            
            # Handle cases where the row may not have exactly 2 columns
            if len(cells) != 2:
                continue
                
            tool_name, test_prompt = cells
            
            # Parse the tool name to extract service and command
            # For tool names like "azmcp-foundry-models-list", we want ["foundry", "foundry_models_list"]
            expected_tool_calls = []
            
            if tool_name.startswith('azmcp-'):
                # Remove the "azmcp-" prefix and work with the rest
                remaining = tool_name[6:]  # Remove "azmcp-"
                
                # Split by dashes and take the first part as service
                parts = remaining.split('-')
                if len(parts) > 0:
                    service_name = parts[0]  # e.g., "foundry"
                    expected_tool_calls.append(service_name)
                    
                    # Create the full command name by joining all parts with underscores
                    full_command = '_'.join(parts)  # e.g., "foundry_models_list"
                    expected_tool_calls.append(full_command)
            else:
                # For other formats, use the original logic
                if '-' in tool_name:
                    service_name = tool_name.split('-')[0]
                    expected_tool_calls.append(service_name)
                    full_tool_name = tool_name.replace('-', '_')
                    expected_tool_calls.append(full_tool_name)
                elif '_' in tool_name:
                    service_name = tool_name.split('_')[0]
                    expected_tool_calls.append(service_name)
                    expected_tool_calls.append(tool_name)
                else:
                    # If no separator, just use the tool name as both service and command
                    expected_tool_calls.append(tool_name)
                    expected_tool_calls.append(tool_name)
                
            test_prompt = test_prompt.replace('\\<', '<').replace('\\>', '>')
            # Create a JSON object for each entry
            entry = {
                "query": test_prompt,
                "expected_tool_calls": expected_tool_calls,
                "service_area": standardized_service_name  # Add service area to track which service this belongs to
            }
            
            results.append(entry)
    
    return results


def find_placeholders_in_text(text):
    """Find all placeholders in the format <...> in the given text"""
    pattern = r'<[^>]+>'
    return re.findall(pattern, text)


def replace_placeholders_and_track_unmapped(data, variable_mappings, service_areas=None):
    """Replace placeholders with fake names and track unmapped ones
    
    Args:
        data: List of entries to process
        variable_mappings: Dictionary of variable mappings to use
        service_areas: List of service area names to filter placeholders (optional)
        
    Returns:
        tuple: (processed_entries, unmapped_placeholders, skipped_entries_count)
    """
    unmapped_placeholders = defaultdict(int)
    
    # Group entries by service area
    entries_by_service = defaultdict(list)
    for entry in data:
        service_area = entry.get('service_area')
        entries_by_service[service_area].append(entry)
    
    processed_entries = []
    skipped_entries_count = 0
    
    # Process each service area separately
    for service_area, entries in entries_by_service.items():
        # Build the mappings to use for this specific service area
        mappings_to_use = {}
        
        # Always include common placeholders
        if "common" in variable_mappings:
            mappings_to_use.update(variable_mappings["common"])
        
        # Add mappings specific to this service area
        if service_area and service_area in variable_mappings:
            mappings_to_use.update(variable_mappings[service_area])
        
        # Process each entry in this service area
        for entry in entries:
            query = entry['query']
            original_query = query  # Keep original for error reporting
            
            # Replace all placeholders in the query using only this service area's mappings
            for placeholder, fake_name in mappings_to_use.items():
                if fake_name is None:
                    continue
                query = query.replace(placeholder, fake_name)
                
            # Check for any remaining unmapped placeholders
            remaining_placeholders = find_placeholders_in_text(query)
            
            if remaining_placeholders:
                # Track unmapped placeholders for reporting
                for placeholder in remaining_placeholders:
                    unmapped_placeholders[placeholder] += 1
                
                # Skip this entry - don't add it to processed_entries
                skipped_entries_count += 1
                print(f"⚠️  Skipping query with unmapped placeholders: {remaining_placeholders}")
                print(f"   Original query: {original_query[:100]}{'...' if len(original_query) > 100 else ''}")
            else:
                # No unmapped placeholders, include this entry
                entry['query'] = query
                processed_entries.append(entry)
    
    return processed_entries, unmapped_placeholders, skipped_entries_count


def save_to_jsonl_file(data, output_file):
    """Save data to a JSONL file"""
    with open(output_file, 'w', encoding='utf-8') as f:
        for entry in data:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')


def log_unmapped_placeholders(unmapped_placeholders, skipped_count=0):
    """Log unmapped placeholders to console"""
    if unmapped_placeholders:
        print("\n⚠️  WARNING: Found unmapped placeholders:")
        print("=" * 50)
        for placeholder, count in sorted(unmapped_placeholders.items()):
            print(f"  {placeholder} (found {count} times)")
        print("=" * 50)
        if skipped_count > 0:
            print(f"Queries with unmapped placeholders were skipped ({skipped_count} total).")
        print("Consider adding these to the variable_mappings dictionary.\n")
    else:
        print("✅ All placeholders successfully mapped!")


def main():
    # Load service header mapping once at the start
    service_header_mapping = load_config_from_json("service_mappings.json")
    
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(description='Convert local e2e test prompts to JSONL format')
    parser.add_argument('--service', type=str, help=f'Filter results to only include entries for the specified service area(s). Use comma-separated values for multiple services. Available services: {", ".join(sorted(set(service_header_mapping.values())))}')
    parser.add_argument('--output', '-o', type=str, default='data.jsonl', help='Output JSONL file name (default: data.jsonl)')

    args = parser.parse_args()
    
    # Define source file and output file
    source_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "..", "e2eTests", "e2eTestPrompts.md")
    output_file = args.output
    
    # Parse service names if provided and validate them
    service_names = None
    if args.service:
        service_names = [service.strip() for service in args.service.split(',')]
        
        # Validate that all provided service names are valid
        valid_services = set(service_header_mapping.values())
        invalid_services = [service for service in service_names if service not in valid_services]
        
        if invalid_services:
            print(f"❌ Error: No support added for service name(s): {', '.join(invalid_services)}")
            print(f"Available services: {', '.join(sorted(valid_services))}")
            return
    else:
        # If no service specified, process all services
        service_names = list(service_header_mapping.values())

    current_variable_mappings = {}
    
    # Always include common mappings
    common_test_settings = load_test_settings_from_file()  # Load default/common settings
    current_variable_mappings["common"] = build_variable_mappings("common", common_test_settings)
    
    # Load service-specific mappings
    for service in service_names:
        service_test_settings = load_test_settings_from_file(service_name=service)
        if service_test_settings:
            current_variable_mappings[service] = build_variable_mappings(service, service_test_settings)
        else:
            # If no service-specific settings, use common settings as fallback
            current_variable_mappings[service] = build_variable_mappings(service, common_test_settings)

    # Read the local markdown file
    print(f"Reading e2e test prompts from local file: {source_file}")
    markdown_content = read_local_markdown_file(source_file)
    
    if markdown_content is None:
        return
        
    if service_names:
        print(f"Parsing markdown and converting to JSONL (filtering for services: {', '.join(service_names)})...")
    else:
        print("Parsing markdown and converting to JSONL...")
        
    # Parse the markdown and convert to JSONL
    jsonl_data = parse_markdown_and_convert_to_jsonl(markdown_content, service_names)
    
    if service_names and not jsonl_data:
        print(f"⚠️  WARNING: No entries found for services '{', '.join(service_names)}'. Please check the service name spelling.")
        print(f"Available services: {', '.join(sorted(set(service_header_mapping.values())))}")
        return
    
    print("Replacing placeholders with values...")
    # Replace placeholders and track unmapped ones
    processed_data, unmapped_placeholders, skipped_count = replace_placeholders_and_track_unmapped(jsonl_data, current_variable_mappings, service_names)
    
    # Save to JSONL file
    save_to_jsonl_file(processed_data, output_file)
    
    # Report results
    print(f"\n✅ Conversion complete!")
    print(f"📄 {len(processed_data)} entries written to {output_file}")
    if skipped_count > 0:
        print(f"⚠️  {skipped_count} entries skipped due to unmapped placeholders")
    
    if args.service:
        print(f"🎯 Filtered for services: {', '.join(service_names)}")
    else:
        print(f"🎯 Processed all services ({len(set(service_header_mapping.values()))} total)")

    # Log any unmapped placeholders
    log_unmapped_placeholders(unmapped_placeholders, skipped_count)


if __name__ == "__main__":
    main()
