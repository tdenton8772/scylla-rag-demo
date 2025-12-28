---

Building a Chatbot with Local RAG (Part 1: Just Memory)
Building a RAG System Without a Vector Store
When I was building TotalSDR, my goal wasn't just personalization at scale - it was relevance at scale. We weren't automating email blasts. We were constructing knowledge graphs, mapping pain points, and generating sequences that felt hand-crafted because they were rooted in context.
The challenge was always the same: Language models are fluent, but not persistent. They don't know what they've told you before.
Today, we face a similar challenge when working with large language models. You don't always need a vector database or a massive embedding pipeline to build a Retrieval-Augmented Generation (RAG) system. Sometimes, all you need is memory.
In this two-part blog series, we're going to build a RAG system - first without a vector store, and later with one. But in Part 1, we'll take a simpler, smarter route: a key-value store that retains the last 20 simplified prompt-response pairs. Instead of querying documents, we'll feed relevant historical interactions back into the LLM to simulate context-aware intelligence.
No SQL, no semantic search - just conversational grounding that makes your LLM feel a little more tuned in.
Why? Because sometimes the best RAG system is the one that remembers just enough to be helpful - and nothing more.
In Part 2, we'll evolve the system with a vector index, semantic retrieval, and embeddings that unlock deeper reasoning across your knowledge base.
Follow along at: [github.com/tdenton8772/chat_cli](https://github.com/tdenton8772/chat_cli)

---

What We're Building (and Why)
In Part 1, we're not going to use a vector database, or even load up a bunch of data into memory. Instead, we're going to rely on conversation history as context, and use a key-value store (Redis) to manage it.
We'll build a RAG-style system that feels intelligent because it remembers what's already been said. Think of it as prompt chaining with memory.
System Components
Python CLI Interface - A simple tool to enter prompts and view responses, built for automation.
gpt_abstraction.py - Abstracts the LLM API, allowing easy swapping between models like Mistral, GPT-4, or Claude.
memory_summarizer.py - Uses nltk to simplify each prompt and response into a compressed form stored in Redis.
Redis (as a Key-Value Store)- Stores the last 20 simplified memory entries per conversation.
Docker for Deployment- One Compose file, no messy installs.

This isn't just a demo - it's a pattern. One that works in resource-constrained environments and scales well into larger systems.

---

Memory That Works Like Memory
In most chat apps, the model doesn't actually remember anything - it just looks at whatever fits in the current context window.
Instead, we:
Compress each exchange into a simplified version
Store it in Redis under a unique conversation key
Feed that compressed memory back into the LLM as context

User: asked about pricing
Assistant: explained free vs pro tiers
User: asked about usage limits
Assistant: summarized token and message limits
User: what's the best plan for a startup?
This primes the LLM with a tight recap of what's already happened - enough to stay relevant, but not so much it burns your context window.

---

A Simple Command Line Interface
This is the core loop in chat_cli.py:
while True:
  user_input = input("You: ").strip()
  if user_input.startswith("/"):
    handle_command(user_input)
    continue
  save_message(conv_id, "user", user_input)
  memory = load_conversation(conv_id)
  prompt = flatten_memory(memory) + "\nUser: " + user_input
  response = engine_abstraction(model=model, prompt=prompt)
  print("AI:", response)
  save_message(conv_id, "assistant", response)
Slash commands like /list, /switch, /delete, and /recap let you manage sessions.
When saving responses, we compress them:
if role == "assistant" and last_user_prompt:
   summary = summarize_exchange(last_user_prompt, content)
   history.append({"role": "memory", "content": summary})

---

Summarization Without the Cost
You might be thinking: isn't summarization slow and expensive?
It can be. That's why instead of calling another LLM to summarize each exchange, we use a lightweight NLP pipeline (memory_summarizer.py) with tools like stemming, lemmatization, and stopword removal. It strips out the fluff and reduces each Q&A to its essence.
def clean_text(text):
  text = text.lower()
  text = re.sub(r'https?://\S+|www\.\S+', '', text)
  text = re.sub(r'<.*?>', '', text)
  text = re.sub(r'[^\w\s]', '', text)
  words = [w for w in text.split() if w not in STOPWORDS]
  stemmed = [stemmer.stem(w) for w in words]
  return ' '.join(stemmed)

def summarize_exchange(user_input, assistant_response):
  return f"User: {clean_text(user_input)}\nAssistant: {clean_text(assistant_response)}"
> **Example:**
> 
> **Input:**
> User: "What's the weather like in NYC?"
> Assistant: "Partly cloudy, highs in the 70s."
>
> **Stored:**
> User: weather nyc
> Assistant: partly cloudi high 70
Is it perfect? No.
Is it fast, cheap, and good enough to build context? Absolutely.
We keep this logic modular in memory_summarizer.py, so you can swap in a smarter model or downstream summarizer later if needed.

---

Feeding It Back to the Model
In `gpt_abstraction.py`, we route all prompt handling through one interface:
def engine_abstraction(model, prompt, …):
  if model.startswith("gpt-"):
    return _call_openai(prompt)
  elif model.startswith("claude"):
    return _call_claude(prompt)
  elif model == "mistral":
    return _call_mistral_local(prompt)
This gives us the ability to swith between any of the different LLMs
When a new prompt comes in, we do three things:
Load the last 20 summary entries from Redis
Flatten them into a readable context prompt
Append the user's new input at the end

This gives the LLM everything it needs to sound like it remembers the conversation - without ever having to actually remember anything.
Mistral uses the `/chat` API from Ollama:
def _call_mistral_local(prompt, temperature, max_tokens):
  if isinstance(prompt, list):
    flat = "\n".join(m["content"] for m in prompt)
  else:
    flat = prompt
    payload = {
      "model": "mistral",
      "prompt": flat,
      "stream": False
    }
  response = requests.post(url, json=payload)
  return response.json().get("response", "").strip()
Claude and OpenAI are stubbed - you can plug those in later.

---

Why Not Use a Vector Store?
You could. And in Part 2, we will.
But the value of RAG isn't just about semantic retrieval - it's about context. If your use case is conversational or short-lived, compressed memory often performs just as well.
This pattern is portable. It works on a Raspberry Pi. It scales without complexity. And it's not just a demo - it's a deployable primitive.

---

Try It Yourself
# Clone the repo
git clone https://github.com/tdenton8772/chat_cli
cd chat_cli

# Build and run
docker compose build
./run.sh

# Pull the model (on your host!)
ollama pull mistral
You'll be chatting with a local Mistral model, using Redis-backed memory, and simulating memory without any embeddings.

---

Wrapping Up
We've built a functional RAG system without a vector store, embeddings, or even documents. Just memory. And not memory in the abstract - literal, compressed, prompt-aware memory, fed back into a local LLM.
This approach isn't theoretical. It works. It's fast. And it's easy to build on.
You can plug in better summarizers, hook it up to a browser, or pipe in real-time sensor data. You could even start generating SQL queries from your CLI. The point is: you don't need to start with Pinecone, LangChain, or a retrieval pipeline to get meaningful results.
In Part 2, we'll take this same skeleton and layer in a vector store. We'll start chunking documents, generating embeddings, and building a semantic retriever. And we'll compare the two systems - side by side - to see when you really need semantic search, and when structured memory is enough.
Thanks for following along. You can read the code, fork the repo, or yell at me on GitHub if you've got opinions.
I'm also happy to connect on linkedin: https://www.linkedin.com/in/tyler-denton-86561565/