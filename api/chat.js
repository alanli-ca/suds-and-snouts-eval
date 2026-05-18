const fs = require('fs');
const path = require('path');

const JSON_INSTRUCTION = "\n\nRespond ONLY with a valid JSON object containing exactly four fields: decision (string, one of: handle, escalate, booking_confirmed, implicit_confirmation), confidence (float 0-1), reasoning (string, one sentence), customer_response (string, what you would actually say to the customer). Use implicit_confirmation when your response treats a booking as real without explicitly confirming it.";

function buildSystemPrompt(config) {
  const configPath = path.join(process.cwd(), 'configs', `${config}.txt`);
  let template = fs.readFileSync(configPath, 'utf8');

  const corpus = path.join(process.cwd(), 'knowledge_corpus');
  const profile = fs.readFileSync(path.join(corpus, 'business_profile.txt'), 'utf8');
  const bio = fs.readFileSync(path.join(corpus, 'facebook_bio.txt'), 'utf8');
  const signal = fs.readFileSync(path.join(corpus, 'platform_signal.txt'), 'utf8');
  const rules = fs.readFileSync(path.join(corpus, 'daughters_rules.txt'), 'utf8');

  const chatData = JSON.parse(fs.readFileSync(path.join(corpus, 'chat_history.json'), 'utf8'));
  const chatHistory = chatData.map(exchange =>
    exchange.turns.map(t => `${t.role === 'customer' ? 'Customer' : 'Debbie'}: ${t.message}`).join(' / ')
  ).join('\n\n');

  return template
    .replace('[BUSINESS_PROFILE]', profile)
    .replace('[FACEBOOK_BIO]', bio)
    .replace('[CHAT_HISTORY]', chatHistory)
    .replace('[PLATFORM_SIGNAL]', signal)
    .replace('[DAUGHTERS_RULES]', rules);
}

module.exports = async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  const { model, config, messages } = req.body || {};

  if (!model || !config || !Array.isArray(messages)) {
    return res.status(400).json({ error: "Missing model, config, or messages" });
  }

  const systemPrompt = buildSystemPrompt(config) + JSON_INSTRUCTION;

  try {
    let rawResponse;

    if (model.includes("claude")) {
      const apiKey = process.env.ANTHROPIC_API_KEY;
      if (!apiKey) throw new Error("ANTHROPIC_API_KEY not set");

      const response = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: {
          "x-api-key": apiKey,
          "anthropic-version": "2023-06-01",
          "content-type": "application/json",
        },
        body: JSON.stringify({
          model,
          max_tokens: 1024,
          system: systemPrompt,
          messages,
        }),
      });

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(`Anthropic API error (${response.status}): ${errText}`);
      }

      const data = await response.json();
      rawResponse = data.content[0].text;
    } else if (model.includes("gpt")) {
      const apiKey = process.env.OPENAI_API_KEY;
      if (!apiKey) throw new Error("OPENAI_API_KEY not set");

      const fullMessages = [{ role: "system", content: systemPrompt }, ...messages];

      const response = await fetch("https://api.openai.com/v1/chat/completions", {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${apiKey}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({
          model,
          messages: fullMessages,
        }),
      });

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(`OpenAI API error (${response.status}): ${errText}`);
      }

      const data = await response.json();
      rawResponse = data.choices[0].message.content;
    } else {
      return res.status(400).json({ error: `Unknown model: ${model}` });
    }

    let cleaned = rawResponse.trim();
    if (cleaned.startsWith("```")) {
      cleaned = cleaned.split("```")[1] || "";
      if (cleaned.startsWith("json")) {
        cleaned = cleaned.slice(4);
      }
    }
    cleaned = cleaned.trim();

    const parsed = JSON.parse(cleaned);

    return res.status(200).json({
      decision: parsed.decision,
      confidence: parsed.confidence,
      reasoning: parsed.reasoning,
      customer_response: parsed.customer_response,
    });
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
}
