# 🧾 AutoSchemaAI - Flat File Reader & Schema Profiler

A powerful **Streamlit-based web application** for exploring, profiling, and analyzing flat files (CSV/TXT) with intelligent schema detection using AI agents, code-based detection, and manual entry modes.

## 🎯 Purpose

AutoSchemaAI streamlines the ETL (Extract, Transform, Load) workflow by:
- **Automatically detecting** file structure (delimiters, encoding, headers)
- **Profiling data** with three intelligent modes: Manual, Code Logic, and AI Agent
- **Exporting schemas** as production-ready SSIS (SQL Server Integration Services) metadata XML

Perfect for data engineers, ETL developers, and data analysts working with legacy flat files.

---

## ✨ Key Features

### 🔍 Smart File Parsing
- Auto-detects delimiters (`,`, `;`, `\t`, `|`, space)
- Detects encoding (UTF-8, Latin-1, UTF-16)
- Recognizes line endings (LF, CRLF, CR)
- Identifies headers automatically
- Supports CSV and TXT files

### 📊 Three Profiling Modes

| Mode | Technology | Use Case |
|------|-----------|----------|
| **Manual** | Form-based UI | Full control over schema definition |
| **Code Logic** | Regex + Pandas | Deterministic pattern matching |
| **AI Agent** | Groq LLama 3.3 70B | Intelligent context-aware detection |

### 📋 Three Main Tabs

#### 1. **Data Table** (`📋 Data Table`)
- View file summaries (rows, columns, size, delimiter)
- Paginated data browsing with configurable start row and row count
- Full-text search across all columns
- Column visibility toggle
- CSV download of filtered view

#### 2. **Data Profiling** (`🔬 Data Profiling`)
- Run any of the three profiling modes
- View detailed per-column analysis:
  - Detected data type
  - Column length
  - Nullability
  - Value patterns
- File metadata (encoding, delimiters, headers)
- Dataset summary (total cells, null values, duplicates)
- SSIS type mappings

#### 3. **Edit & Export** (`✏️ Edit & Export`)
- Edit auto-detected schema inline
- Adjust field properties before export
- Export as SSIS metadata XML
- Ready for SQL Server Integration Services

---

## 🚀 Installation

### Prerequisites
- **Python:** 3.8 or higher
- **pip:** Package manager

### Steps

1. **Clone or download the project**
   ```bash
   cd m:\Python\AI-ML\AutoSchemaAI
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure API credentials** (for AI Agent mode)
   - Open `config.ini`
   - Add your Groq API key:
     ```ini
     [groq]
     api_key = <your_groq_api_key_here>
     ```
   - Get a free API key from [Groq Console](https://console.groq.com)

4. **Run the application**
   ```bash
   streamlit run app.py
   ```
   Or using Python module:
   ```bash
   python -m streamlit run app.py
   ```

5. **Open in browser**
   - Local: `http://localhost:8501`
   - Network: `http://<your_ip>:8501`

---

## 📖 Usage Guide

### Basic Workflow

```
START
  ↓
[1. Upload CSV/TXT File]
  ↓
[2. Auto-detect Configuration]
  ├─ Delimiter detection
  ├─ Encoding detection
  ├─ Line ending detection
  └─ Header identification
  ↓
[3. Parse into DataFrame]
  ↓
[4. Explore in Data Table Tab]
  ├─ View summary metrics
  ├─ Browse rows with pagination
  ├─ Search & filter columns
  └─ Download filtered CSV
  ↓
[5. Profile Data (Select Mode)]
  ├─ Option A: Manual - Enter schema manually
  ├─ Option B: Code Logic - Auto-detect with rules
  └─ Option C: AI Agent - Intelligent detection
  ↓
[6. Review Profiling Results]
  ├─ File metadata
  ├─ Per-column profiles
  ├─ Data quality metrics
  └─ SSIS type suggestions
  ↓
[7. Edit & Export]
  ├─ Refine detected schema
  ├─ Adjust data types
  ├─ Edit field properties
  └─ Export as SSIS XML
  ↓
END
```

### Detailed Tab Features

#### 📋 **Tab 1: Data Table**

**Access:** Click the "📋 Data Table" tab after uploading a file

**Features:**
1. **Summary Metrics**
   - Total rows, number of columns, file size, delimiter

2. **View Controls**
   - `Start from row`: Choose which row to begin viewing (0-indexed)
   - `Number of rows to display`: Rows to show per page (default: 10)

3. **Search**
   - Full-text search box to find specific values across all columns

4. **Column Selection**
   - Toggle which columns to display/hide

5. **Download**
   - Download current view as CSV file

**Example:**
```
Total rows: 10,000 | Columns: 25 | File size: 2.5 MB | Delimiter: ,
Start from row: 100 | Show 50 rows | [Search...] [Select Columns]
╔════════════════════════════════════════════════════════════╗
║ ID  │ Name        │ Email         │ Age  │ City           ║
╠════════════════════════════════════════════════════════════╣
║ 101 │ John Doe    │ john@test.com │ 28  │ New York       ║
║ 102 │ Jane Smith  │ jane@test.com │ 34  │ Los Angeles    ║
...
```

#### 🔬 **Tab 2: Data Profiling**

**Access:** Click the "🔬 Data Profiling" tab

**Available Modes:**

**A. Manual Mode**
- Fill in a form for each column
- Specify: Name, data type, length, nullability, patterns
- **Best for:** Complete control, edge cases, business logic

**B. Code Logic Mode**
- Automatic detection using regex patterns and pandas analysis
- **Best for:** Consistent, rule-based files, speed

**C. AI Agent Mode**
- Uses Groq API (LLama 3.3 70B) with tool-calling loop
- Intelligent schema inference
- Context-aware type detection
- **Best for:** Complex files, semantic understanding

**Output for All Modes:**

1. **File Metadata Table**
   - Field delimiter, line ending, text delimiter
   - Has headers, encoding, file size

2. **Dataset Summary**
   - Total cells, null values, duplicates
   - Row and column counts

3. **Per-Column Profile Table**
   ```
   Field Name │ Predicted Type │ Length │ Nullable │ Sample Values
   ──────────────────────────────────────────────────────────────
   id         │ Integer        │ 8      │ No       │ 1, 2, 3
   email      │ Email Address  │ 254    │ Yes      │ user@test.com
   salary     │ Numeric        │ 10     │ No       │ 50000.00
   ```

4. **Null Values Heatmap**
   - Visual representation of missing data by column

5. **SSIS Export**
   - Suggested SQL Server Integration Services data types

#### ✏️ **Tab 3: Edit & Export**

**Access:** Click the "✏️ Edit & Export" tab (after running a profile)

**Features:**

1. **Load Profile**
   - Automatically loads the most recent profile (AI, Code, or Manual)

2. **Inline Editing**
   - Edit field name, predicted type, SSIS type
   - Adjust length, nullable flag
   - Modify line endings, delimiters, encoding

3. **SSIS Export**
   - Generate production-ready SSIS metadata XML
   - Direct integration with SQL Server
   - Download XML file for import

**Example XML Output:**
```xml
<?xml version="1.0" encoding="utf-8"?>
<DtsObject Name="YourFile.csv">
  <Property Name="FieldDelimiter">,</Property>
  <Property Name="HasHeaders">true</Property>
  <Columns>
    <Column Name="id" DataType="DT_I4" Length="8" Nullable="false"/>
    <Column Name="email" DataType="DT_STR" Length="254" Nullable="true"/>
    <Column Name="salary" DataType="DT_NUMERIC" Nullable="false"/>
  </Columns>
</DtsObject>
```

---

## 📁 Project Structure

```
AutoSchemaAI/
│
├── app.py                          # Main Streamlit entry point
├── config.ini                      # Groq API configuration
├── requirements.txt                # Python dependencies
├── Prompt.txt                      # AI agent system prompt
├── README.md                       # This file
│
├── core/                           # Core parsing logic (no Streamlit)
│   ├── __init__.py
│   ├── config.py                  # Configuration loader (API keys, models)
│   └── file_parser.py             # Flat file parsing (pandas DataFrame)
│
├── profiling/                      # Profiling engines
│   ├── __init__.py
│   ├── agent.py                   # AI agent (Groq LLama 3.3) orchestrator
│   └── detectors.py               # Rule-based detection functions
│
├── ssis/                           # SSIS export functionality
│   ├── __init__.py
│   └── type_mapper.py             # Maps detected types to SSIS types
│
└── ui/                             # Streamlit UI components
    ├── __init__.py
    ├── tab_data_table.py          # Data table tab
    ├── tab_profiling.py           # Data profiling tab
    └── tab_edit_export.py         # Edit & export tab
```

---

## 🔧 Module Reference

### **core/config.py**
**Purpose:** Configuration management
- Loads Groq API key from `config.ini`
- Exposes `GROQ_API_KEY`, `GROQ_MODEL` constants
- Validates configuration before app startup

### **core/file_parser.py**
**Purpose:** File parsing only (no side effects)
- `resolve_separator()`: Auto-detects delimiters
- `parse_flat_file()`: Converts bytes → pandas DataFrame
- Supports delimiter choice (auto, `,`, `;`, `\t`, `|`)
- Handles encoding and skip-rows options

### **profiling/detectors.py**
**Purpose:** Rule-based detection helpers
- `detect_line_ending()`: Identifies line terminators
- `detect_text_delimiter()`: Finds quoted text delimiters
- `build_file_metadata()`: Assembles file-level metadata
- Column-level detection (types, patterns, nullability)
- **Used by:** Code Logic mode and AI agent tools

### **profiling/agent.py**
**Purpose:** AI orchestration
- `run_agent()`: Main tool-calling loop with Groq API
- Manages conversation context
- Iteratively refines schema detection
- Fallback to code detection if AI fails

### **ssis/type_mapper.py**
**Purpose:** SSIS export functionality
- Maps detected types to SQL Server SSIS types
- `build_ssis_xml()`: Generates SSIS metadata XML
- Handles SSIS data type mappings:
  - Text → DT_STR
  - Integer → DT_I4
  - Float → DT_R8
  - Date → DT_DBDATE
  - etc.

### **ui/tab_data_table.py**
**Purpose:** Data exploration interface
- Metric display (rows, columns, size, delimiter)
- Pagination controls (start row, row count)
- Full-text search across DataFrame
- Column visibility toggle
- CSV download

### **ui/tab_profiling.py**
**Purpose:** Profiling modes interface
- Mode selection (Manual, Code, AI)
- Form for manual entry
- Triggers code/AI detection
- Displays results with tables, heatmaps, metrics
- Shows SSIS suggestions

### **ui/tab_edit_export.py**
**Purpose:** Schema refinement and export
- Loads cached profile from session state
- Inline editing of schema properties
- SSIS XML generation and download
- Pre-populated dropdowns for common choices

---

## 🔑 Configuration

### **config.ini**
Located in the project root directory.

**Example:**
```ini
[groq]
api_key = gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Get your API key:**
1. Visit [Groq Console](https://console.groq.com)
2. Sign up (free tier available)
3. Create an API key
4. Paste into `config.ini`

**Models Available:**
- `llama-3.3-70b-versatile` (default) - Best overall balance
- `mixtral-8x7b-32768` - Faster alternative
- Others available through Groq API

---

## 📦 Dependencies

See `requirements.txt`:
```
streamlit>=1.35.0      # Web framework
pandas>=2.0.0          # Data manipulation
requests>=2.31.0       # HTTP client (Groq API calls)
```

**Installation:**
```bash
pip install -r requirements.txt
```

---

## 🎓 Examples

### Example 1: Profile a CSV with AI Agent

1. Download a CSV file with customer data
2. Click "Run the app" → upload your CSV
3. In `🔬 Data Profiling` tab:
   - Select "AI Agent" mode
   - Click "Run AI Profiling"
   - Wait 30-60 seconds for analysis
4. Review detected schema
5. In `✏️ Edit & Export`:
   - Refine any fields if needed
   - Click "Download SSIS XML"

### Example 2: Manual Schema Definition

1. Upload a exotic CSV with custom delimiters
2. Go to `🔬 Data Profiling`
3. Select "Manual" mode
4. Fill in form for each column
5. Specify exact data types and lengths
6. Export to SSIS XML

### Example 3: Quick Data Exploration

1. Upload file
2. Stay in `📋 Data Table` tab
3. Use pagination and search to explore
4. Download filtered result as CSV
5. No profiling needed

---

## 🐛 Troubleshooting

### **Issue: "Error: File does not exist: app.py"**
**Solution:** Make sure you're in the correct directory:
```bash
cd m:\Python\AI-ML\AutoSchemaAI
python -m streamlit run app.py
```

### **Issue: "ModuleNotFoundError: No module named 'streamlit'"**
**Solution:** Install dependencies:
```bash
pip install -r requirements.txt
```

### **Issue: "GROQ_API_KEY not found"**
**Solution:** 
1. Create/update `config.ini` in project root
2. Add your Groq API key:
   ```ini
   [groq]
   api_key = your_key_here
   ```

### **Issue: AI Agent times out**
**Solution:**
- Check internet connection
- Verify Groq API key is valid
- Try a smaller file first
- Use Code Logic mode as fallback

### **Issue: File encoding errors**
**Solution:**
- Try different encoding (UTF-8, Latin-1, UTF-16)
- Check file origin (Windows/Linux line endings)
- Use `file_parser.py` directly to debug

---

## 🚦 Performance Tips

| Action | Best Practice |
|--------|----------------|
| **Large files** | Upload <100MB CSV for best UI responsiveness |
| **Many columns** | Use column selector to hide unused fields |
| **AI profiling** | Use on 1,000-10,000 row samples for speed |
| **Multiple files** | Session state auto-clears when new file uploaded |

---

## 🔄 Workflow Summary

```
┌─────────────────────────────────────────┐
│  1. UPLOAD                              │
│     └─ Auto-detect file config          │
└──────────────┬──────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│  2. EXPLORE                             │
│     ├─ View data table                  │
│     ├─ Search & filter                  │
│     └─ Download samples                 │
└──────────────┬──────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│  3. PROFILE (Choose Mode)               │
│     ├─ Manual (user-defined)            │
│     ├─ Code Logic (rule-based)          │
│     └─ AI Agent (intelligent)           │
└──────────────┬──────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│  4. REVIEW                              │
│     ├─ Metadata & metrics               │
│     ├─ Per-column profiles              │
│     └─ Data quality summary             │
└──────────────┬──────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│  5. EDIT & EXPORT                       │
│     ├─ Refine schema                    │
│     ├─ Adjust data types                │
│     └─ Export as SSIS XML               │
└─────────────────────────────────────────┘
```

---

## 📞 Support

For issues or questions:
1. Check the **Troubleshooting** section above
2. Review the code comments in relevant modules
3. Verify configuration in `config.ini`
4. Check Groq API status at [console.groq.com](https://console.groq.com)

---

## 📄 License

This project is proprietary software.  
All rights reserved © 2026

---

## 🎯 Roadmap

Future enhancements:
- [ ] Support for JSON/XML/Parquet files
- [ ] Database connectivity (direct SQL table ingestion)
- [ ] Data quality rule validation
- [ ] Schema versioning & history
- [ ] Batch processing mode
- [ ] REST API for headless usage
- [ ] Schema templates and library

---

**Made with ❤️ by Infinite Hackathon H1 2026 - Cotiviti EDM RCA Retail AutoSchemaAI Team**

Last Updated: April 7, 2026
