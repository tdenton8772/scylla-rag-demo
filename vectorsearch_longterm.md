---

Building a Chatbot with Local RAG (Part 2: Vectors)
TL;DR
In Part 2 of this series, we take our simple RAG chatbot and make it smarter by adding long-term memory with vector search. Using Mistral (via Ollama) for embeddings and FAISS for fast local vector storage, we unlock semantic recall: the ability to remember the meaning of what was said, not just the exact words. It's still local, lightweight, and modular.
Clone the code: https://github.com/tdenton8772/chat_cli_vector

---

A Quick Recap
In Part 1, we built a local chatbot using a key-value memory model with Redis. It worked well for recency-based recall, but had one big limitation: it only remembered exact messages.
Now we're fixing that by adding vector search. This means the chatbot can:
Recall meaning, not just phrases
Find related ideas even if phrased differently
Hold onto long-term memory across restarts

Why Vectors?
Key-value memory is good for immediate recall.
But to build a chatbot that feels more intelligent, we need memory that can answer questions like:
"Where do I live again?"
"What are my hobbies?"
"Remind me what I told you about my family."

These don't require exact matches - they require understanding.
With vector search, we embed each message into a list of numbers that encode meaning. Then we use FAISS to search for similar meanings later on.
What We Built in Part 2
Local embeddings using Mistral via Ollama
A persistent FAISS vector store
A hybrid memory system that combines:
Redis for short-term (last 5 messages)
FAISS for long-term (semantic search)
A modular chatbot CLI that wires it all together

Project Structure (Compared to Part 1)
We added just a few new files:
chat_cli_vector/
├── embedding.py # NEW: calls Ollama for vector embeddings
├── vector_store.py # NEW: wraps FAISS and adds persistence
├── hybrid_memory.py # NEW: merges Redis and vector memory
├── config.py # NEW: top_k, dim, model name
├── chat_cli.py # UPDATED: now uses hybrid memory
The rest is the same: run.sh, gpt_abstraction.py, memory_summarizer.py, etc.

---

How Vector Memory Works
Step 1: Generate Embeddings
We use Mistral running locally via Ollama. Our embedding.py just posts to the Ollama embedding endpoint:
response = requests.post(
 "http://ollama:11434/api/embeddings",
 json={"model": "mistral", "prompt": text}
)
No API keys. Fully local.
Step 2: Store in FAISS
Each user input and assistant summary is embedded and stored in FAISS with a conv_id tag.
vector_store.add(
 text="My name is Tyler and I live in Florida",
 embedding=get_embedding(…),
 metadata={"conv_id": "abc-123", "source": "user"}
)
We also persist FAISS to disk using .write_index() and save metadata in JSON. That way memory survives container restarts.
Step 3: Search the Vector Store
When the user asks something new, we embed it and search for the top 4 similar messages:
hits = vector_store.search(
 embedding=get_embedding(user_input),
 top_k=4,
 conv_id=conv_id # filter results to current chat
)
Because FAISS doesn't support metadata filtering directly, we overfetch and filter by conv_id manually.
Step 4: Build Hybrid Context
We merge:
Vector hits (long-term recall)
Redis memory (short-term recency)
The user prompt

context = vector_hits + kv_memory + [{"role": "user", "content": user_input}]
Then we pass that to the model using gpt_abstraction.py.
Running a Demo Chat
Once it's wired up, run it with:
./run.sh
Then try this sequence:
You: My name is Tyler and I live in Florida.
You: My wife is a nurse and we have three dogs.
You: I love sailing and working on drone footage.
Later:
You: What do you know about my pets?
You: Where do I live again?
If vector memory is working, you'll see those past lines pulled in from FAISS - even if they've aged out of Redis.
You can view them live:
/vectors
Memory Tuning & Pitfalls
As you start testing, you might notice the chatbot repeating your inputs, missing key details, or pulling in irrelevant context. These are normal issues that show up as your memory system gets more sophisticated. Here are the main things to watch out for:
1. Vector Echoes
If the chatbot seems to just repeat back exactly what you just said, it might be because the vector search is returning your current input as a hit. Since we embed user input and store it immediately, it's possible to pull that same input right back in the next vector query.
We prevent this by filtering out any vector hits that match the input too closely. You can do this with a simple exact match check, or get more nuanced using something like difflib.SequenceMatcher to fuzz-match high-similarity strings.
2. Redis Too Deep
If your Redis MAX_HISTORY is set too high, the short-term memory buffer might dominate the context. That leaves no room for FAISS vector hits in the prompt - and your model ends up working with just recency, not relevance.
We found that trimming this down to 5 memory entries keeps the conversation grounded without crowding out the semantic hits from FAISS. Of course, this value can be tuned based on how verbose your prompts and summaries are.
3. FAISS is Global
FAISS is fast, but it's dumb about context. It doesn't understand sessions, users, or anything beyond a list of vectors. This means that memories from one conversation can bleed into another - leading to confusing or irrelevant responses.
To work around this, we store a conv_id with each vector and post-filter the search results to only return matches from the active conversation. It's not perfect (and not fast at large scale), but it keeps your chatbot from confusing one user's memories with another's.
4. No Metadata Filtering
Related to the above: FAISS does not support metadata filtering natively. You can't say "give me the 5 closest matches where conv_id = x" - you have to fetch a bunch of results and manually filter after the fact.
This is fine for small indexes, but it doesn't scale well. As your chatbot grows - or as you begin indexing additional memory types - this limitation becomes a bottleneck. For serious projects, you'll want to look at vector databases like Pinot, Qdrant, Weaviate, or Chroma that support structured filtering at query time.
All of these tuning decisions are about balancing clarity and context. You want the model to see the most relevant information - not just the most recent or most similar. It's a subtle game, but it makes all the difference.
Wrapping Up
In Part 2, we made the chatbot smarter by teaching it to remember meaning, not just messages. Now it:
Remembers facts across restarts
Handles semantically phrased follow-up questions
Supports long-term memory on a lightweight, local stack

All of this without an API key, hosted model, or external service.
Coming Next in Part 3
Right now we only store user input and assistant replies. But what if we added:
External documents
Troubleshooting guides
Enriched background info

In Part 3, we'll show how to turn this memory system into a knowledge base - and how to fine-tune your chatbot's behavior using its own stored history.
Until then: clone the repo, try it out, and maybe ask your bot where you live. It might just remember.
I'm also happy to connect on linkedin: https://www.linkedin.com/in/tyler-denton-86561565/