import os
import sys
import json
import yaml
import csv
import subprocess
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def load_config(config_path="structure_data/config.yaml"):
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

def load_system_prompt(prompt_path):
    try:
        with open(f"structure_data/{prompt_path}", "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        print(f"Error loading prompt: {e}")
        sys.exit(1)

def process_data():
    config = load_config()
    
    input_json_path = config.get("input_json")
    output_csv_path = config.get("output_csv")
    sample_size = config.get("sample_size")
    text_keys = config.get("text_keys_to_read", [])
    keep_keys = config.get("keep_keys", [])
    prompt_file = config.get("prompt_file")
    
    llm_config = config.get("llm", {})
    provider = llm_config.get("provider", "openai")
    model = llm_config.get("model", "gpt-4o-mini")
    base_url = llm_config.get("base_url")
    api_key_env_var = llm_config.get("api_key_env_var")
    
    system_prompt = load_system_prompt(prompt_file)
    
    # Initialize LLM Client
    # Both OpenAI and Ollama can use the OpenAI Python SDK
    # Ollama acts as an OpenAI-compatible endpoint at http://localhost:11434/v1
    api_key = "dummy_key_for_ollama" if provider == "ollama" else os.getenv(api_key_env_var or "OPENAI_API_KEY")


    if not api_key:
        print(f"Error: API Key needed. Export {api_key_env_var} or set properly for {provider}.")
        sys.exit(1)

    # Manage Ollama model lifecycle
    if provider == "ollama":
        print(f"Downloading/Updating Ollama model '{model}'...")
        try:
            subprocess.run(["ollama", "pull", model], check=True)
            print(f"Successfully pulled Ollama model '{model}'.")
        except subprocess.CalledProcessError as e:
            print(f"Error pulling Ollama model '{model}': {e}")
            sys.exit(1)
        except FileNotFoundError:
            print("Error: 'ollama' command not found. Is Ollama installed and in your PATH?")
            sys.exit(1)

    base_url = None
    client = OpenAI(
        api_key=api_key,
        base_url=base_url if base_url else None
    )

    # Load JSON Input
    try:
        with open(input_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading input JSON {input_json_path}: {e}")
        # Clean up if ollama was pulled
        if provider == "ollama":
            subprocess.run(["ollama", "rm", model], check=False)
        sys.exit(1)
        
    if sample_size is not None:
        data = data[:int(sample_size)]
        
    print(f"Loaded {len(data)} records (Sample Size limit applied). Connecting to {provider.upper()} model '{model}'...")

    results = []
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0
    
    try:
        for idx, item in enumerate(data, 1):
            # Extract text payload for LLM
            payload_parts = []
            author_name = item.get("author", "Unknown")
            payload_parts.append(f"Author: {author_name}")
            
            for tk in text_keys:
                val = item.get(tk)
                if val:
                    payload_parts.append(f"{tk}:\n{str(val)}")
            
            combined_text = "\n\n".join(payload_parts)
            
            print(f"Processing record {idx}/{len(data)}...")
            
            structured_data = {}
            if combined_text.strip():
                try:
                    # Call LLM
                    response = client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": f"Extract details from this text:\n\n{combined_text}"}
                        ],
                        response_format={ "type": "json_object" } if provider == "openai" else None,
                        temperature=1.0
                    )
                    
                    content = response.choices[0].message.content.strip()
                    
                    # Cleanup markdown formatting if model didn't listen
                    if content.startswith("```json"):
                        content = content[7:]
                    if content.startswith("```"):
                        content = content[3:]
                    if content.endswith("```"):
                        content = content[:-3]
                    
                    # Track tokens and compute cost
                    input_tokens = 0
                    output_tokens = 0
                    cost = 0.0
                    if hasattr(response, "usage") and response.usage:
                        input_tokens = getattr(response.usage, "prompt_tokens", 0)
                        output_tokens = getattr(response.usage, "completion_tokens", 0)
                        
                        if "gpt-4o-mini" in model:
                            cost = (input_tokens / 1000000 * 0.150) + (output_tokens / 1000000 * 0.600)
                        elif "gpt-4o" in model:
                            cost = (input_tokens / 1000000 * 5.00) + (output_tokens / 1000000 * 15.00)
                        elif "gpt-3.5" in model:
                            cost = (input_tokens / 1000000 * 0.50) + (output_tokens / 1000000 * 1.50)
                        elif "gpt-5-nano" in model:
                            cost = (input_tokens / 1000000 * 0.05) + (output_tokens / 1000000 * 0.4)

                        total_input_tokens += input_tokens
                        total_output_tokens += output_tokens
                        total_cost += cost
                        
                    # Store the exact LLM text response in a log file as requested
                    with open("structure_data/raw_llm_responses.txt", "a", encoding="utf-8") as f:
                        f.write(f"--- Record {idx} ---\n{content}\n\n")
                        
                    try:
                        structured_data = json.loads(content.strip())
                    except json.JSONDecodeError:
                        structured_data = {"raw_response": content.strip()}
                        
                    structured_data["input_tokens"] = input_tokens
                    structured_data["output_tokens"] = output_tokens
                    structured_data["cost_usd"] = f"{cost:.5f}"
                    
                except Exception as e:
                    print(f"  -> Error calling LLM or parsing JSON: {e}")
            else:
                print(f"  -> Skipping LLM call (no text to process)")
                
            # Combine native keep_keys with structured data
            final_row = {}
            final_row.update(structured_data)

            for kk in keep_keys:
                final_row[kk] = item.get(kk, "")
                
            results.append(final_row)
            

        results.append({
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "cost_usd": f"{total_cost:.5f}"
        })

        # Write to CSV
        if results:
            # Get all unique fieldnames
            fieldnames = []
            seen_keys = set()
            for res in results:
                for k in res.keys():
                    if k not in seen_keys:
                        fieldnames.append(k)
                        seen_keys.add(k)
                        
            try:
                with open(output_csv_path, "w", encoding="utf-8", newline="") as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(results)
                print(f"\nDone! Structured data saved to {output_csv_path}")
            except Exception as e:
                print(f"Error saving CSV: {e}")

    finally:
        # Cleanup Ollama model
        if provider == "ollama":
            print(f"\nCleaning up: Deleting Ollama model '{model}' from local storage...")
            try:
                subprocess.run(["ollama", "rm", model], check=True)
                print(f"Successfully deleted Ollama model '{model}'.")
            except Exception as e:
                print(f"Error deleting Ollama model '{model}': {e}")

if __name__ == "__main__":
    process_data()
