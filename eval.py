import json
import os
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
MODEL_NAMES = ["claude", "gpt4o"]

JSON_INSTRUCTION = (
    "\n\nRespond ONLY with a valid JSON object containing exactly three fields: "
    '"decision" (string, one of: "handle", "escalate", "booking_confirmed"), '
    '"confidence" (float between 0 and 1), '
    '"reasoning" (string, one sentence). '
    "Do not include any other text."
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

        if model_name == "claude":
            client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
            create_kwargs = dict(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{"role": "user", "content": customer_message}],
            )
            if system_prompt.strip():
                create_kwargs["system"] = system_prompt
            response = client.messages.create(**create_kwargs)
            raw_response = response.content[0].text
        elif model_name == "gpt4o":
            client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
            messages = []
            if system_prompt.strip():
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": customer_message})
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
            )
            raw_response = response.choices[0].message.content
        else:
            raise ValueError(f"Unknown model_name: {model_name}")

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

            if model_name == "claude":
                client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
                create_kwargs = dict(
                    model="claude-sonnet-4-6",
                    max_tokens=1024,
                    messages=conversation,
                )
                if system_prompt.strip():
                    create_kwargs["system"] = system_prompt
                response = client.messages.create(**create_kwargs)
                raw_response = response.content[0].text
            elif model_name == "gpt4o":
                client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
                messages = []
                if system_prompt.strip():
                    messages.append({"role": "system", "content": system_prompt})
                messages.extend(conversation)
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                )
                raw_response = response.choices[0].message.content
            else:
                raise ValueError(f"Unknown model_name: {model_name}")

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
                "raw_response": raw_response,
            })

            final_decision = decision
            if decision == "booking_confirmed":
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


def main():
    RESULTS_DIR.mkdir(exist_ok=True)
    test_cases = load_test_cases()
    results = []
    for test_case in test_cases:
        tc_id = test_case.get("id", "unknown")
        tc_type = test_case.get("type")
        for config_name in CONFIG_NAMES:
            for model_name in MODEL_NAMES:
                print(f"Running test case {tc_id} through {config_name} / {model_name}...")
                if tc_type == "multi_message":
                    result = run_eval_multi(test_case, config_name, model_name)
                else:
                    result = run_eval(test_case, config_name, model_name)
                results.append(result)
    with open(RESULTS_DIR / "raw_results.json", "w") as f:
        json.dump(results, f, indent=2)


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
            print(f"  Turn {turn_resp['turn']}: decision={turn_resp['decision']} | reasoning={turn_resp['reasoning']}")
        print(f"Final decision: {result.get('final_decision')}")
        print(f"Break turn: {result.get('break_turn')}")
    else:
        result = run_eval(test_case, config_name, model_name)
        print(f"Decision: {result.get('decision')}")
        print(f"Confidence: {result.get('confidence')}")
        print(f"Reasoning: {result.get('reasoning')}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 4:
        run_single_test(sys.argv[1], sys.argv[2], sys.argv[3])
    else:
        main()
