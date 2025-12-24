import os
from flask import Flask, render_template, request
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    p_data = request.form.to_dict()
    
    # Döküman kriterlerini (S,O,T,Y tipleri, normalizasyon tabloları) zorunlu kılan Master Prompt
    master_prompt = f"""
    You are a Senior Database Architect. Project Details: {p_data}
    
    Provide a professional database report in ENGLISH using ONLY raw HTML tags. 
    Match the output style to a modern dashboard.

    STAGE 1: Project Definition Summary.
    
    STAGE 2: Business Rules. Create a <table> with these exact columns: 
    [BR-ID, Rule Type (S,O,T,Y), Rule Statement, ER Component (E/R/A/C), Implementation Tip, Rationale]. [cite: 35-43]
    
    STAGE 3: Table Definitions. For each entity, create an HTML table showing: 
    [Table Name (Plural), Attribute, Data Type, Constraints (PK, FK, UK, NOT NULL, CHECK), Description]. [cite: 46-55]
    
    STAGE 4: Missing Rules. Create a <table> with: [Missing Rule, Related BR, Proposed Solution]. [cite: 59]
    
    STAGE 5: Normalization (0NF to 3NF). Provide FOUR separate HTML tables. 
    Label them as 0NF, 1NF, 2NF, and 3NF. Explain the logic of removing partial and transitive dependencies below each table. [cite: 62-66]
    
    STAGE 6: ER Diagram. Provide ONLY: <div class="mermaid">erDiagram ...</div> using Crow's Foot notation. [cite: 68]
    
    STAGE 7: SQL Generation. Provide: CREATE TABLE, ALTER TABLE, 1 TRIGGER, 1 VIEW, 1 ROLE, and 3 sample SELECT queries inside <pre> tags. [cite: 70-74]

    CRITICAL: Do not use markdown (```). Use only standard HTML.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "You are a DB expert. Output strictly HTML tables and blocks."},
                      {"role": "user", "content": master_prompt}]
        )
        # Markdown temizleme işlemi
        clean_content = response.choices[0].message.content.replace("```html", "").replace("```mermaid", "").replace("```", "").strip()
        
        return render_template('results.html', content=clean_content, domain=p_data['domain'])
    except Exception as e:
        return f"System Error: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True)