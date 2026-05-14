# KnowledgeVault Setup Guide

A step-by-step guide for setting up KnowledgeVault without technical expertise.

---

## What You Need Before Starting

### Required Items

- [ ] A computer running Windows 10/11, macOS, or Linux
- [ ] At least 8GB of RAM (16GB recommended)
- [ ] At least 10GB of free disk space
- [ ] Internet connection
- [ ] Documents you want to upload (Word, PDF, Excel, etc.)

### Software to Install First

1. **Docker Desktop** - This runs the application
   - Download from: https://www.docker.com/products/docker-desktop
   - Follow the installation wizard
   - Restart your computer if prompted

2. **Ollama** - This provides the AI brain
   - Download from: https://ollama.com
   - Run the installer
   - Ollama will start automatically

---

## Step-by-Step Setup

### Step 1: Install Docker Desktop

**[SCREENSHOT PLACEHOLDER: Docker Desktop download page]**

1. Go to https://www.docker.com/products/docker-desktop
2. Click "Download Docker Desktop"
3. Choose your operating system
4. Run the downloaded installer
5. Follow the installation prompts
6. When finished, Docker Desktop will open

**[SCREENSHOT PLACEHOLDER: Docker Desktop running with green status]**

Wait for Docker Desktop to show a green "Running" status before continuing.

---

### Step 2: Install Ollama

**[SCREENSHOT PLACEHOLDER: Ollama website download page]**

1. Go to https://ollama.com
2. Click "Download"
3. Choose your operating system
4. Run the installer
5. Ollama will start automatically in the background

**[SCREENSHOT PLACEHOLDER: Terminal showing Ollama is running]**

To verify Ollama is running:

**Windows:**
1. Open Command Prompt (press Windows key + R, type "cmd", press Enter)
2. Type: `ollama list`
3. Press Enter
4. You should see a list (possibly empty)

**Mac:**
1. Open Terminal (press Command + Space, type "terminal", press Enter)
2. Type: `ollama list`
3. Press Enter

**Linux:**
1. Open a terminal
2. Type: `ollama list`
3. Press Enter

---

### Step 3: Download AI Models

KnowledgeVault needs two AI models to work:

#### Model 1: Embedding Model (Required)

This model helps understand your documents.

**[SCREENSHOT PLACEHOLDER: Terminal showing model download]**

The embedding service (Harrier) is automatically downloaded and started by Docker Compose on first launch — you do not need to install it manually.

1. Open your terminal/command prompt
2. Start KnowledgeVault and Harrier will download automatically:
   ```
   docker compose up -d
   ```
3. The first startup may take a few minutes while Harrier (~1.2GB) downloads

#### Model 2: Chat Model (Choose One)

This model answers your questions. Choose based on your computer:

**Option A - Fast and Small (Good for most computers):**
```
ollama pull llama3.2:latest
```

**Option B - Smart and Large (Needs 22GB+ RAM):**
```
ollama pull qwen2.5:32b
```

**[SCREENSHOT PLACEHOLDER: Terminal showing model download complete]**

To download, type your chosen command and press Enter.

Wait for the download to finish before continuing.

---

### Step 4: Get KnowledgeVault Files

**[SCREENSHOT PLACEHOLDER: File explorer showing repo folder]**

1. Get the KnowledgeVault files from your administrator (the repository folder)
2. Place the folder where you can find it easily
3. Remember this location - you will need it later

Example locations:
- Windows: `C:\Users\YourName\ragappv3`
- Mac: `/Users/YourName/ragappv3`
- Linux: `/home/YourName/ragappv3`

---

### Step 5: Configure KnowledgeVault

**[SCREENSHOT PLACEHOLDER: File explorer showing .env.example file]**

1. Open the KnowledgeVault folder
2. Find the file named `.env.example`
3. Make a copy of this file
4. Rename the copy to `.env` (just `.env`, nothing before the dot)

**[SCREENSHOT PLACEHOLDER: Text editor showing .env file contents]**

5. Open the `.env` file in a text editor (Notepad, TextEdit, etc.)
6. Find the line: `HOST_DATA_DIR=./data`
7. Change it to a full path where you want to store your data

**Examples:**

Windows:
```
HOST_DATA_DIR=C:\Users\YourName\KnowledgeVault\data
```

Mac:
```
HOST_DATA_DIR=/Users/YourName/KnowledgeVault/data
```

Linux:
```
HOST_DATA_DIR=/home/YourName/KnowledgeVault/data
```

**[SCREENSHOT PLACEHOLDER: .env file with updated data path]**

8. If you chose a different chat model in Step 3, update this line:
   - Find: `CHAT_MODEL=qwen2.5:32b`
   - Change to: `CHAT_MODEL=llama3.2:latest` (or whatever you chose)

9. Save the file and close the editor

---

### Step 6: Start KnowledgeVault

**[SCREENSHOT PLACEHOLDER: Terminal in KnowledgeVault folder]**

1. Open your terminal/command prompt
2. Navigate to your KnowledgeVault folder:

**Windows:**
```
cd C:\Users\YourName\ragappv3
```

**Mac/Linux:**
```
cd /Users/YourName/ragappv3
```

**[SCREENSHOT PLACEHOLDER: Terminal showing docker compose command]**

3. Type this command:
   ```
   docker compose up -d --build
   ```
4. Press Enter
5. Wait for the command to finish (this may take a few minutes the first time)

**[SCREENSHOT PLACEHOLDER: Docker Desktop showing running containers]**

6. Open Docker Desktop
7. You should see "knowledgevault" in the Containers list
8. The status should show "Running" with a green dot

---

### Step 7: Open KnowledgeVault in Your Browser

**[SCREENSHOT PLACEHOLDER: Browser showing KnowledgeVault login page]**

1. Open your web browser (Chrome, Firefox, Safari, or Edge)
2. Type this in the address bar:
   ```
   http://localhost:9090
   ```
3. Press Enter
4. KnowledgeVault should load

**[SCREENSHOT PLACEHOLDER: KnowledgeVault main interface]**

You should see the KnowledgeVault interface with a navigation menu on the left.

---

## Using KnowledgeVault

### Upload Your First Document

**[SCREENSHOT PLACEHOLDER: Documents page with upload button]**

1. Click "Documents" in the left menu
2. Click the "Upload" button
3. Select a document from your computer
4. Click "Open"
5. Wait for the upload to complete

**[SCREENSHOT PLACEHOLDER: Document showing processing status]**

The document will show a status:
- "Pending" - Waiting to process
- "Processing" - Currently being analyzed
- "Complete" - Ready to use
- "Error" - Something went wrong

Wait for "Complete" before asking questions about the document.

---

### Ask a Question

**[SCREENSHOT PLACEHOLDER: Chat page with question being typed]**

1. Click "Chat" in the left menu
2. Type your question in the box at the bottom
3. Press Enter or click the Send button
4. Wait for the AI to respond

**[SCREENSHOT PLACEHOLDER: Chat showing AI response with sources]**

The AI will:
- Show its response as it types
- List the documents it referenced
- Let you click to see the source

---

### Save Important Information

**[SCREENSHOT PLACEHOLDER: Chat showing "Remember that" command]**

To save information for later:

1. In the chat, type: "Remember that [your information]"
2. Example: "Remember that the server password is xyz123"
3. Press Enter
4. The AI will confirm it saved the memory

To view saved memories:
1. Click "Memory" in the left menu
2. See all your saved memories
3. Use the search box to find specific memories

---

## Daily Use Checklist

### Starting KnowledgeVault

- [ ] Open Docker Desktop
- [ ] Verify Ollama is running (type `ollama list` in terminal)
- [ ] Open browser to http://localhost:9090

### Shutting Down KnowledgeVault

To stop KnowledgeVault when you're done:

1. Open terminal
2. Navigate to the ragappv3 folder
3. Type: `docker compose down`
4. Press Enter

Or simply close Docker Desktop.

---

## Troubleshooting

### "Cannot connect to server" Error

**[SCREENSHOT PLACEHOLDER: Error message in browser]**

**Problem:** Browser cannot find KnowledgeVault

**Solution:**
1. Check Docker Desktop is running
2. Check the knowledgevault container shows "Running"
3. Try refreshing the browser page
4. Wait 30 seconds and try again

### "LLM Unavailable" Warning

**[SCREENSHOT PLACEHOLDER: Status showing LLM unavailable]**

**Problem:** KnowledgeVault cannot connect to Ollama

**Solution:**
1. Check Ollama is running:
   - Open terminal
   - Type: `ollama list`
   - You should see your models listed
2. If Ollama is not running, restart it
3. Refresh the KnowledgeVault page

### Documents Stuck on "Pending"

**[SCREENSHOT PLACEHOLDER: Document list showing pending status]**

**Problem:** Documents are not being processed

**Solution:**
1. Wait 5 minutes (processing takes time)
2. Check Docker Desktop logs:
   - Click on the knowledgevault container
   - Click "Logs" tab
   - Look for error messages
3. Restart KnowledgeVault:
   ```
   docker compose restart
   ```

### Slow Responses

**Problem:** AI takes a long time to respond

**Solutions:**
1. Use a smaller, faster model (llama3.2 instead of qwen2.5:32b)
2. Close other programs to free up RAM
3. Upload fewer documents at once
4. Be patient - first response may be slow

### Out of Memory Error

**Problem:** Computer runs out of RAM

**Solutions:**
1. Use a smaller chat model
2. Close other applications
3. Process documents in smaller batches
4. Add more RAM to your computer

---

## Getting Help

If you encounter problems:

1. Check the logs in Docker Desktop
2. Ask your system administrator
3. Check the README.md file for technical details
4. Check the admin-guide.md for advanced troubleshooting

---

## Quick Reference Card

### Important Commands

| What You Want | Command |
|---------------|---------|
| Start KnowledgeVault | `docker compose up -d --build` |
| Stop KnowledgeVault | `docker compose down` |
| Restart KnowledgeVault | `docker compose restart` |
| View logs | `docker compose logs` |
| Check Ollama | `ollama list` |
| Download model | `ollama pull [model-name]` |

### Important URLs

| Service | URL |
|---------|-----|
| KnowledgeVault | http://localhost:9090 |
| API Documentation | http://localhost:9090/docs |

### Supported File Types

| Type | Extension |
|------|-----------|
| Word Documents | .docx |
| Excel Spreadsheets | .xlsx |
| PowerPoint | .pptx |
| PDF Files | .pdf |
| Text Files | .txt |
| CSV Files | .csv |
| SQL Files | .sql |
| Code Files | .py, .js, .java, etc. |

---

## Setup Complete Checklist

- [ ] Docker Desktop installed and running
- [ ] Ollama installed and running
- [ ] Harrier embedding service started (auto-configured via docker-compose)
- [ ] Chat model downloaded (llama3.2 or qwen2.5:32b)
- [ ] KnowledgeVault files extracted
- [ ] .env file configured with correct paths
- [ ] KnowledgeVault started with `docker compose up -d`
- [ ] Web interface accessible at http://localhost:9090
- [ ] Test document uploaded successfully
- [ ] Test question answered successfully

**Congratulations! You are ready to use KnowledgeVault.**
