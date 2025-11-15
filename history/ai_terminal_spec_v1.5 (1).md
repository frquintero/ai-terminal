# AI-Powered Terminal Specification (v1.5)

## 1. Overview
The AI-powered terminal operates in cycles, each rendered in its own REPL pane.  
Each cycle contains exactly two elements:

1. **User Query** — plain text  
2. **AI Final Response** — structured text that always includes plain text and may optionally include fenced blocks.

Every cycle is assigned a **unique Cycle ID**, generated fresh for each cycle.  
It appears as plain text in the **bottom-right corner** of the pane:

```
Cycle ID: 9f32-b817-4421
```

---

## 2. Cycle Structure

### 2.1 User Query
- Raw text  
- No markdown  
- Can be natural language or direct shell commands  
- Submitted when the user presses **Enter**  
- Triggers the internal system phases: **Planning → Executing → Building Response**

### 2.2 System Phase Indicators
After submission, the system cycles through three temporary indicators:

- **[Planning…]**  
- **[Executing…]**  
- **[Building Response…]**

### Single-line Real-Time Indicator Behavior
- Indicators appear on **the same fixed line** in the pane.  
- Only **one indicator** is shown at a time.  
- Each new indicator **replaces** the previous one.  
- Just before the AI final response is displayed, the indicator line is **removed completely**.

---

## 3. AI Final Response
- Always contains plain text  
- May optionally include fenced blocks  
- Accepted patterns:
  - Text only  
  - Text + fenced block  
  - Text + fenced block + trailing text  
- The AI response is *not* wrapped in an outer fence block.

---

## 4. Internal Sub-Block Types

| Block Tag | Purpose |
|-----------|----------|
| `hydrate` | System introspection before executing |
| `plan` | Ordered execution steps |
| `bash` | Commands to run |
| `output` | Shell output |
| `json` | Machine-readable data |
| `log` | Logs |
| `md`  | Optional markdown snippet |

---

## 5. Recommended Ordering Inside AI Responses

1. Introductory text  
2. Hydration block (optional)  
3. Plan block (optional)  
4. Commands block (optional)  
5. Output block (optional)  
6. JSON block (optional)  
7. Closing text  

Example format:

Preparing environment…

```plan
1. …
2. …
```

```bash
…
```

```output
…
```

All tasks completed.

---

## 6. System Phase Example

A user submits:

`build the docker image`

The pane shows:

```
[Planning…]
```

Then:

```
[Executing…]
```

Then:

```
[Building Response…]
```

Just before the AI final response, this line disappears.

---

## 7. Full Example Cycle

### User Query
`set up a python project with venv and install fastapi`

### AI Final Response
Setting up the Python environment…

```plan
1. python3 -m venv .venv
2. source .venv/bin/activate
3. pip install fastapi uvicorn
4. pip freeze > requirements.txt
```

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn
pip freeze > requirements.txt
```

```output
Successfully installed fastapi-0.110 uvicorn-0.27
```

Environment ready.

```
Cycle ID: 6c1c-9a02-44fb
```

Each new cycle displays its **own unique ID**.

---

## 8. Rendering & Parsing Rules

- One cycle per pane  
- Pane includes:
  - The user query  
  - The single-line real-time phase indicator (temporary)  
  - The AI final response  
  - The unique Cycle ID  
- Temporary indicators never appear in stored output  
- AI response always includes plain text  
- Sub-blocks are optional  

---

## 9. Extensibility

New sub-block types may be added if:
- They remain fenced blocks  
- They appear inside the AI response  
- They maintain backward compatibility

