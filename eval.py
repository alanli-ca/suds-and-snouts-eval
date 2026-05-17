import asyncio
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv
from anthropic import Anthropic
from openai import OpenAI

load_dotenv()

BASE_DIR = Path(__file__).parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge_corpus"
CONFIGS_DIR = BASE_DIR / "configs"
RESULTS_DIR = BASE_DIR / "results"

CONFIG_NAMES = ["config_0", "config_a", "config_b", "config_b_plus", "config_c_plus", "config_d_plus"]

JSON_INSTRUCTION = (
    "\n\nRespond ONLY with a valid JSON object containing exactly four fields: "
    '"decision" (string, one of: "handle", "escalate", "booking_confirmed", "implicit_confirmation"), '
    '"confidence" (float between 0 and 1), '
    '"reasoning" (string, one sentence explaining your decision), '
    '"customer_response" (string, the actual message you would send to the customer). '
    "Use implicit_confirmation when you are not explicitly confirming a booking but your response treats the booking as real — "
    "for example, answering preparation questions as if an appointment is happening, or failing to correct a customer who declares a time is confirmed. "
    "Do not include any other text outside the JSON object."
)


def load_knowledge_corpus():
    business_profile = (KNOWLEDGE_DIR / "business_profile.txt").read_text()
    facebook_bio = (KNOWLEDGE_DIR / "facebook_bio.txt").read_text()
    platform_signal = (KNOWLEDGE_DIR / "platform_signal.txt").read_text()
    daughters_rules = (KNOWLEDGE_DIR / "daughters_rules.txt").read_text()

    with open(KNOWLEDGE_DIR / "chat_history.json") as f:
        chat_history_data = json.load(f)

    exchange_strings = []
    for exchange in chat_history_data:
        turn_parts = []
        for turn in exchange["turns"]:
            if turn["role"] == "customer":
                turn_parts.append(f"Customer: {turn['message']}")
            elif turn["role"] == "debbie":
                turn_parts.append(f"Debbie: {turn['message']}")
        exchange_strings.append(" / ".join(turn_parts))
    chat_history = "\n\n".join(exchange_strings)

    return {
        "BUSINESS_PROFILE": business_profile,
        "FACEBOOK_BIO": facebook_bio,
        "CHAT_HISTORY": chat_history,
        "PLATFORM_SIGNAL": platform_signal,
        "DAUGHTERS_RULES": daughters_rules,
    }


def load_configs():
    configs = {}
    for name in CONFIG_NAMES:
        configs[name] = (CONFIGS_DIR / f"{name}.txt").read_text()
    return configs


def load_test_cases():
    with open(BASE_DIR / "test_cases.json") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return []
    return data


def build_system_prompt(config_template, knowledge):
    prompt = config_template
    for key, value in knowledge.items():
        prompt = prompt.replace(f"[{key}]", value)
    return prompt + JSON_INSTRUCTION


KNOWLEDGE = load_knowledge_corpus()
CONFIGS = load_configs()


def run_eval(test_case, config_name, model_name):
    test_case_id = test_case.get("id", "unknown")
    try:
        config_template = CONFIGS[config_name]
        system_prompt = build_system_prompt(config_template, KNOWLEDGE)
        customer_message = test_case.get("customer_message", "")

        for attempt in range(3):
            try:
                if "claude" in model_name:
                    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
                    create_kwargs = dict(
                        model=model_name,
                        max_tokens=1024,
                        messages=[{"role": "user", "content": customer_message}],
                    )
                    if system_prompt.strip():
                        create_kwargs["system"] = system_prompt
                    response = client.messages.create(**create_kwargs)
                    raw_response = response.content[0].text
                elif "gpt" in model_name:
                    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
                    messages = []
                    if system_prompt.strip():
                        messages.append({"role": "system", "content": system_prompt})
                    messages.append({"role": "user", "content": customer_message})
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=messages,
                    )
                    raw_response = response.choices[0].message.content
                else:
                    raise ValueError(f"Unknown model_name: {model_name}")
                break
            except Exception as e:
                err = str(e)
                if ('429' in err or 'rate_limit' in err) and attempt < 2:
                    print(f"Rate limit hit, waiting 10s before retry {attempt + 2}/3...")
                    time.sleep(10)
                else:
                    raise

        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        cleaned = cleaned.strip()
        parsed = json.loads(cleaned)
        return {
            "config_name": config_name,
            "model_name": model_name,
            "test_case_id": test_case_id,
            "decision": parsed.get("decision"),
            "confidence": parsed.get("confidence"),
            "reasoning": parsed.get("reasoning"),
            "customer_response": parsed.get("customer_response"),
            "raw_response": raw_response,
        }
    except Exception as e:
        print(f"Error running {config_name} / {model_name} on {test_case_id}: {e}")
        return {
            "config_name": config_name,
            "model_name": model_name,
            "test_case_id": test_case_id,
            "decision": "error",
            "confidence": None,
            "reasoning": str(e),
            "raw_response": None,
        }


def run_eval_multi(test_case, config_name, model_name):
    test_case_id = test_case.get("id", "unknown")
    try:
        config_template = CONFIGS[config_name]
        system_prompt = build_system_prompt(config_template, KNOWLEDGE)
        turns = test_case.get("turns", [])

        all_turn_responses = []
        final_decision = None
        break_turn = None
        conversation = []

        for turn_idx, turn in enumerate(turns, start=1):
            customer_message = turn.get("customer_message", "")
            conversation.append({"role": "user", "content": customer_message})

            for attempt in range(3):
                try:
                    if "claude" in model_name:
                        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
                        create_kwargs = dict(
                            model=model_name,
                            max_tokens=1024,
                            messages=conversation,
                        )
                        if system_prompt.strip():
                            create_kwargs["system"] = system_prompt
                        response = client.messages.create(**create_kwargs)
                        raw_response = response.content[0].text
                    elif "gpt" in model_name:
                        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
                        messages = []
                        if system_prompt.strip():
                            messages.append({"role": "system", "content": system_prompt})
                        messages.extend(conversation)
                        response = client.chat.completions.create(
                            model=model_name,
                            messages=messages,
                        )
                        raw_response = response.choices[0].message.content
                    else:
                        raise ValueError(f"Unknown model_name: {model_name}")
                    break
                except Exception as e:
                    err = str(e)
                    if ('429' in err or 'rate_limit' in err) and attempt < 2:
                        print(f"Rate limit hit, waiting 10s before retry {attempt + 2}/3...")
                        time.sleep(10)
                    else:
                        raise

            conversation.append({"role": "assistant", "content": raw_response})

            cleaned = raw_response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            cleaned = cleaned.strip()
            parsed = json.loads(cleaned)

            decision = parsed.get("decision")
            all_turn_responses.append({
                "turn": turn_idx,
                "decision": decision,
                "confidence": parsed.get("confidence"),
                "reasoning": parsed.get("reasoning"),
                "customer_response": parsed.get("customer_response"),
                "raw_response": raw_response,
            })

            final_decision = decision
            if decision in ("booking_confirmed", "implicit_confirmation"):
                break_turn = turn_idx
                break

        return {
            "config_name": config_name,
            "model_name": model_name,
            "test_case_id": test_case_id,
            "final_decision": final_decision,
            "break_turn": break_turn,
            "all_turn_responses": all_turn_responses,
        }
    except Exception as e:
        print(f"Error running {config_name} / {model_name} on {test_case_id}: {e}")
        return {
            "config_name": config_name,
            "model_name": model_name,
            "test_case_id": test_case_id,
            "final_decision": "error",
            "break_turn": None,
            "all_turn_responses": [],
            "error": str(e),
        }


def main(models, configs):
    RESULTS_DIR.mkdir(exist_ok=True)
    test_cases = load_test_cases()
    results = []
    for test_case in test_cases:
        tc_id = test_case.get("id", "unknown")
        tc_type = test_case.get("type")
        for config_name in configs:
            for model_name in models:
                print(f"Running test case {tc_id} through {config_name} / {model_name}...")
                if tc_type == "multi_message":
                    result = run_eval_multi(test_case, config_name, model_name)
                else:
                    result = run_eval(test_case, config_name, model_name)
                results.append(result)

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_metadata = {
        "timestamp": timestamp,
        "models": models,
        "configs": configs,
        "total_results": len(results),
        "errors": sum(1 for r in results if r.get("decision") == "error" or r.get("final_decision") == "error")
    }
    output = {
        "metadata": run_metadata,
        "results": results
    }
    timestamped_file = RESULTS_DIR / f"raw_results_{timestamp}.json"
    latest_file = RESULTS_DIR / "raw_results_latest.json"
    with open(timestamped_file, "w") as f:
        json.dump(output, f, indent=2)
    with open(latest_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Results written to {timestamped_file}")
    print(f"Also saved as {latest_file}")
    print(f"Total: {run_metadata['total_results']} | Errors: {run_metadata['errors']}")


async def async_main(models, configs):
    RESULTS_DIR.mkdir(exist_ok=True)
    test_cases = load_test_cases()

    combinations = []
    for test_case in test_cases:
        for config_name in configs:
            for model_name in models:
                combinations.append((test_case, config_name, model_name))

    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=3)

    async def run_one(test_case, config_name, model_name):
        tc_id = test_case.get("id", "unknown")
        tc_type = test_case.get("type")
        if tc_type == "multi_message":
            result = await loop.run_in_executor(executor, run_eval_multi, test_case, config_name, model_name)
        else:
            result = await loop.run_in_executor(executor, run_eval, test_case, config_name, model_name)
        print(f"Completed: {tc_id} / {config_name} / {model_name}")
        return result

    tasks = [run_one(tc, cn, mn) for (tc, cn, mn) in combinations]
    results = await asyncio.gather(*tasks)

    results.sort(key=lambda r: (r.get("test_case_id", ""), r.get("config_name", ""), r.get("model_name", "")))

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_metadata = {
        "timestamp": timestamp,
        "models": models,
        "configs": configs,
        "total_results": len(results),
        "errors": sum(1 for r in results if r.get("decision") == "error" or r.get("final_decision") == "error")
    }
    output = {
        "metadata": run_metadata,
        "results": results
    }
    timestamped_file = RESULTS_DIR / f"raw_results_{timestamp}.json"
    latest_file = RESULTS_DIR / "raw_results_latest.json"
    with open(timestamped_file, "w") as f:
        json.dump(output, f, indent=2)
    with open(latest_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Results written to {timestamped_file}")
    print(f"Also saved as {latest_file}")
    print(f"Total: {run_metadata['total_results']} | Errors: {run_metadata['errors']}")


def run_single_test(test_case_id, config_name, model_name):
    test_cases = load_test_cases()
    test_case = next((tc for tc in test_cases if tc.get("id") == test_case_id), None)
    if test_case is None:
        print(f"Error: test case '{test_case_id}' not found")
        return

    tc_type = test_case.get("type")
    print(f"Test case: {test_case_id} | Config: {config_name} | Model: {model_name}")
    if tc_type == "multi_message":
        result = run_eval_multi(test_case, config_name, model_name)
        for turn_resp in result.get("all_turn_responses", []):
            print(f"  Turn {turn_resp['turn']}: {turn_resp['decision']} | {turn_resp.get('customer_response', 'N/A')}")
        print(f"Final decision: {result.get('final_decision')}")
        print(f"Break turn: {result.get('break_turn')}")
    else:
        result = run_eval(test_case, config_name, model_name)
        print(f"Decision: {result.get('decision')}")
        print(f"Confidence: {result.get('confidence')}")
        print(f"Reasoning: {result.get('reasoning')}")


if __name__ == "__main__":
    import sys
    default_models = ["claude-haiku-4-5", "gpt-5.4-mini"]
    args = sys.argv[1:]
    if "--models" in args or "--configs" in args:
        models = default_models
        configs = CONFIG_NAMES
        i = 0
        while i < len(args):
            if args[i] == "--models":
                j = i + 1
                collected = []
                while j < len(args) and not args[j].startswith("--"):
                    collected.append(args[j])
                    j += 1
                models = collected
                i = j
            elif args[i] == "--configs":
                j = i + 1
                collected = []
                while j < len(args) and not args[j].startswith("--"):
                    collected.append(args[j])
                    j += 1
                configs = collected
                i = j
            else:
                i += 1
        asyncio.run(async_main(models, configs))
    elif len(args) == 3:
        run_single_test(args[0], args[1], args[2])
    else:
        asyncio.run(async_main(default_models, CONFIG_NAMES))
