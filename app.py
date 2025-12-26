import os
import json
import re
import mysql.connector
from flask import Flask, render_template, request, jsonify
from openai import OpenAI
from dotenv import load_dotenv

# .env dosyasındaki API anahtarını yükle
load_dotenv()

app = Flask(__name__)
# API Key kontrolü
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------------------------------------------------------
# SİHİRLİ FONKSİYON: OTOMATİK TRIGGER ENJEKSİYONU
# Bu fonksiyon veritabanı yapısına bakar ve uygun triggerları kendisi ekler.
# ---------------------------------------------------------
def inject_smart_triggers(cursor, db_name):
    """
    Tabloları analiz eder. Product, Patient veya Order tablolarına göre
    otomatik trigger (tetikleyici) oluşturur.
    """
    print(f"--- [Smart Trigger] Analiz Başlıyor: {db_name} ---")
    
    # 1. Mevcut tabloları listele
    cursor.execute("SHOW TABLES")
    tables = [x[0] for x in cursor.fetchall()]
    print(f"Tespit Edilen Tablolar: {tables}")
    
    # --- SENARYO 1: E-TİCARET (Products Tablosu Varsa) ---
    if 'products' in tables:
        try:
            cursor.execute("DROP TRIGGER IF EXISTS trg_auto_check_price")
            # Not: Kodun 'price' sütunu olduğunu varsayar. AI genelde price üretir.
            sql = """
            CREATE TRIGGER trg_auto_check_price
            BEFORE INSERT ON products
            FOR EACH ROW
            BEGIN
                IF NEW.price < 0 THEN
                    SIGNAL SQLSTATE '45000'
                    SET MESSAGE_TEXT = 'Hata: Urun fiyati 0 dan kucuk olamaz!';
                END IF;
            END
            """
            cursor.execute(sql)
            print("✅ [Products] Fiyat koruma kuralı eklendi.")
        except Exception as e:
            print(f"⚠️ Products trigger hatası (Sütun adı farklı olabilir): {e}")

    # --- SENARYO 2: HASTANE (Patients Tablosu Varsa) ---
    if 'patients' in tables:
        try:
            cursor.execute("DROP TRIGGER IF EXISTS trg_auto_check_patient")
            # Generic bir kontrol: İsim boş olamaz.
            sql = """
            CREATE TRIGGER trg_auto_check_patient
            BEFORE INSERT ON patients
            FOR EACH ROW
            BEGIN
                IF NEW.full_name = '' OR NEW.full_name IS NULL THEN
                     SIGNAL SQLSTATE '45000'
                     SET MESSAGE_TEXT = 'Hata: Hasta adi (full_name) bos olamaz!';
                END IF;
            END
            """
            cursor.execute(sql)
            print("✅ [Patients] Hasta doğrulama kuralı eklendi.")
        except Exception as e:
            print(f"⚠️ Patients trigger hatası: {e}")

    # --- SENARYO 3: SİPARİŞ & STOK (Orders ve Products Varsa) ---
    if 'orders' in tables and 'products' in tables:
        try:
            cursor.execute("DROP TRIGGER IF EXISTS trg_auto_reduce_stock")
            sql = """
            CREATE TRIGGER trg_auto_reduce_stock
            AFTER INSERT ON orders
            FOR EACH ROW
            BEGIN
                UPDATE products 
                SET stock_quantity = stock_quantity - NEW.quantity
                WHERE product_id = NEW.product_id;
            END
            """
            cursor.execute(sql)
            print("✅ [Orders] Otomatik stok düşme kuralı eklendi.")
        except Exception as e:
            print(f"⚠️ Orders trigger hatası: {e}")

def get_master_prompt(p_data, fix_rule=None):
    """
    Stage 1-7 Mimari Motoru (FULL SÜRÜM).
    """
    fix_instruction = ""
    
    # Varsayılan tablo içeriği (AI dolduracak)
    stage2_content_injection = "[AI: Generate 10 detailed rows showing complex business logic and how they are enforced in the DB.]"
    
    # Eğer kullanıcı 'Fix This Gap' butonuna bastıysa:
    if fix_rule:
        safe_rule = str(fix_rule).replace("'", "").replace('"', '')
        
        fix_instruction = f"""
        \n\n⚠️ CRITICAL UPDATE REQUESTED BY USER: 
        The user detected a missing rule: '{safe_rule}'.
        You MUST re-design the entire system (Stages 1-7) to accommodate this new rule.
        - Update the Business Rules table.
        - Update the Table Structure (add columns if needed).
        - Update the SQL Triggers to enforce this logic if applicable.
        """
        
        fixed_row_html = f"""
        <tr style="display:none;" class="hidden-log-row">
            <td class="p-4">GAP-LOG</td>
            <td class="p-4">Deleted Logic: {safe_rule}</td>
            <td class="p-4">LOG</td>
        </tr>
        <tr class="bg-emerald-900/40 border-l-4 border-emerald-500">
            <td class="p-4 font-black text-emerald-400">FIX-APPLIED</td>
            <td class="p-4 font-bold text-white uppercase">{safe_rule}</td>
            <td class="p-4 text-emerald-300 font-mono">CRITICAL CONSTRAINT</td>
        </tr>
        """
        
        stage2_content_injection = f"""
        {fixed_row_html}
        [AI: I have already injected the fix log above. Now generate 8 more standard business rules rows below it. 
        Do not repeat the fixed rule. Keep the other rows neutral styling.]
        """

    master_prompt = f"""
    You are a Senior Database Architect specialized in MySQL / MariaDB (XAMPP Environment).
    PROJECT DOMAIN: {p_data.get('domain')}
    PRIMARY ENTITY: {p_data.get('primary_entity')}
    USER CONSTRAINTS: {p_data.get('constraints')}
    {fix_instruction}
    
    ----------------------------------------------------------------------
    CRITICAL DATABASE RULES (YOU MUST FOLLOW THESE OR THE SQL WILL FAIL):
    ----------------------------------------------------------------------
    1. **SIMPLIFIED SCHEMA FOR TRIGGERS**: 
       - Even though real-world apps use `order_items`, for this simplified demo, the `orders` table MUST directly contain:
         - `product_id` (INT, Foreign Key to products)
         - `quantity` (INT)
       - DO NOT create a separate `order_items` table. Put the product link in `orders`.
       
    2. **TRIGGER COMPATIBILITY**: 
       - Your triggers will run on `orders`.
       - Therefore, when writing triggers, you MUST use `NEW.product_id` and `NEW.quantity`.
       - If you don't put these columns in the `orders` table, the SQL will crash with "Unknown column".
       
    3. **SQL SYNTAX**:
       - Use `DELIMITER $$` for triggers.
       - Always start triggers with `DROP TRIGGER IF EXISTS name$$`.
       - End triggers with `END$$` and then `DELIMITER ;`.
    
    ----------------------------------------------------------------------
    OUTPUT FORMAT:
    ----------------------------------------------------------------------
    - Return ONLY raw HTML code. 
    - NO markdown code blocks (```). 
    - NO preamble text.
    - The output must be ready to be injected into a `div`.

    <div id="stage1" style="display:block;">
        <h3 class="text-3xl font-black border-b-4 border-blue-500 pb-2 mb-6 uppercase text-white">1. Executive Summary</h3>
        <div class="space-y-6 text-slate-300 text-lg leading-relaxed">
            <p><strong>Architecture Overview:</strong> [AI: Write 2 paragraphs describing the {p_data.get('domain')} system architecture.]</p>
            <p><strong>Technical Stack:</strong> MySQL (InnoDB Engine), Flask Python, TailwindCSS Frontend.</p>
        </div>
    </div>

    <div id="stage2" style="display:none;">
        <h3 class="text-2xl font-bold border-b-2 border-blue-500 pb-2 mb-4 text-white">2. Business Rules & Constraints</h3>
        <table class="w-full text-left bg-slate-900/80 rounded-xl overflow-hidden border border-slate-700">
            <thead class="bg-blue-600/30 text-blue-300 uppercase text-xs">
                <tr><th class="p-4">ID</th><th class="p-4">Rule Description</th><th class="p-4">Enforcement Type</th></tr>
            </thead>
            <tbody class="text-slate-300 text-sm">
                {stage2_content_injection}
            </tbody>
        </table>
    </div>

    <div id="stage3" style="display:none;">
        <h3 class="text-2xl font-bold border-b-2 border-blue-500 pb-2 mb-6 text-white">3. Table Structures</h3>
        <div class="grid grid-cols-1 gap-8">
            [AI: Generate HTML Tables for the schema. 
            IMPORTANT: Visually confirm that the `orders` table has `product_id` and `quantity` fields listed.]
        </div>
    </div>

    <div id="stage4" style="display:none;">
        <h3 class="text-2xl font-bold border-b-2 border-blue-500 pb-2 mb-6 text-white">4. Logic Gaps & Audit</h3>
        <div class="grid grid-cols-1 gap-4">
            [AI: Create 4 GAP CARDS. Each card must have a specific missing rule logic.
            Format:
            <div class="p-5 bg-slate-900 border-l-4 border-amber-500 rounded-xl flex justify-between items-center text-white mb-4">
                <div><h4 class="font-bold text-amber-500">MISSING LOGIC</h4><p class="text-slate-400 text-sm">Description...</p></div>
                <button class="bg-blue-600 hover:bg-blue-500 px-6 py-2 rounded-xl font-bold transition" onclick="fixMissingRule('FIX_CONTENT')">FIX IT 🚀</button>
            </div>
            ]
        </div>
    </div>

    <div id="stage5" style="display:none;">
        <h3 class="text-2xl font-bold border-b-2 border-blue-500 pb-2 mb-6 text-white">5. Normalization Process (0NF to 3NF)</h3>
        <div class="space-y-8">
            <div class="bg-red-900/20 p-6 rounded-xl border border-red-800">
                <h4 class="text-xl font-bold text-red-400 mb-4">0NF (Unnormalized Form)</h4>
                <p class="text-slate-400 text-sm mb-4">Raw data with repeating groups and mixed entities.</p>
                <div class="overflow-x-auto">
                    [AI: Generate a messy HTML table representing 0NF data.
                     Style: <table class="w-full text-xs text-slate-300 border border-slate-700">
                     Include mixed columns like "Customer Name, Product 1, Price 1, Product 2, Price 2" in one row.]
                </div>
            </div>

            <div class="bg-orange-900/20 p-6 rounded-xl border border-orange-800">
                <h4 class="text-xl font-bold text-orange-400 mb-4">1NF (First Normal Form)</h4>
                <p class="text-slate-400 text-sm mb-4">Atomicity ensured. Repeating groups removed.</p>
                <div class="overflow-x-auto">
                     [AI: Generate an HTML table showing 1NF status. All columns atomic.]
                </div>
            </div>

            <div class="bg-yellow-900/20 p-6 rounded-xl border border-yellow-800">
                <h4 class="text-xl font-bold text-yellow-400 mb-4">2NF (Second Normal Form)</h4>
                <p class="text-slate-400 text-sm mb-4">Partial dependencies removed. (Tables split by Primary Keys).</p>
                <div class="grid grid-cols-2 gap-4">
                     [AI: Generate 2 small HTML tables showing separation (e.g., Orders and Products separated).]
                </div>
            </div>

            <div class="bg-emerald-900/20 p-6 rounded-xl border border-emerald-800">
                <h4 class="text-xl font-bold text-emerald-400 mb-4">3NF (Third Normal Form)</h4>
                <p class="text-slate-400 text-sm mb-4">Transitive dependencies removed. Final Schema Structure.</p>
                <div class="grid grid-cols-3 gap-4">
                     [AI: Generate 3 small HTML tables showing final structure (Customers, Products, Orders).]
                </div>
            </div>
        </div>
    </div>

    <div id="stage6" style="display:none;">
        <h3 class="text-2xl font-bold border-b-2 border-blue-500 pb-2 mb-4 text-white">6. Entity Relationship Diagram</h3>
        <div class="mermaid-container bg-slate-900 p-8 rounded-2xl border border-slate-800 flex justify-center">
            <pre class="mermaid-src" style="display:none;">
                erDiagram
                [AI: Generate Mermaid ERD code. 
                Ensure `orders` is connected to `products` directly.
                Do not use special characters or Turkish characters in Mermaid syntax.]
            </pre>
            <div class="mermaid-target"></div>
        </div>
    </div>

    <div id="stage7" style="display:none;">
        <h3 class="text-2xl font-bold border-b-2 border-blue-500 pb-2 mb-4 text-white">7. Production SQL (XAMPP Ready)</h3>
        
        <h4 class="text-xl font-bold text-blue-400 mt-8 mb-2 px-2 border-l-4 border-blue-500">7.1. DDL Script (Structure)</h4>
        <pre class="bg-slate-950 p-6 rounded-2xl border border-blue-900/50 text-blue-200 font-mono text-xs overflow-x-auto shadow-lg">
[AI: WRITE 'CREATE TABLE IF NOT EXISTS' STATEMENTS.
CRITICAL: The `orders` table MUST be:
CREATE TABLE IF NOT EXISTS orders (
    order_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    product_id INT NOT NULL,  <-- MUST BE HERE
    quantity INT NOT NULL,    <-- MUST BE HERE
    order_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);
]
        </pre>

        <h4 class="text-xl font-bold text-emerald-400 mt-8 mb-2 px-2 border-l-4 border-emerald-500">7.2. Seed Data (Mock Data)</h4>
        <pre class="bg-slate-950 p-6 rounded-2xl border border-emerald-900/50 text-emerald-200 font-mono text-xs overflow-x-auto shadow-lg">
[AI: WRITE 'INSERT INTO' STATEMENTS.
- Insert 5 customers.
- Insert 5 products.
- Insert 5 orders (Make sure to include values for `product_id` and `quantity`).]
        </pre>

        <h4 class="text-xl font-bold text-purple-400 mt-8 mb-2 px-2 border-l-4 border-purple-500">7.3. Advanced Triggers</h4>
        <div class="bg-purple-900/10 border border-purple-500/30 p-4 rounded-xl mb-4">
            <p class="text-purple-200 text-sm">⚠️ The system will automatically inject optimized triggers for these tables.</p>
        </div>
        <pre class="bg-slate-950 p-6 rounded-2xl border border-purple-500/50 text-purple-300 font-mono text-xs overflow-x-auto shadow-2xl">
[AI: WRITE 3 TRIGGERS USING 'DELIMITER $$'.
- TRIGGER 1: Check Stock Before Order
- TRIGGER 2: Customer Email Format
- TRIGGER 3: Auto-Subtract Stock
]
        </pre>
    </div>
    """
    
    return master_prompt

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    p_data = request.form.to_dict()
    prompt = get_master_prompt(p_data)
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a Senior Database Architect. Output ONLY valid HTML code. Do not output markdown code blocks."},
                {"role": "user", "content": prompt}
            ]
        )
        content = response.choices[0].message.content.replace("```html", "").replace("```", "").strip()
        return render_template('results.html', content=content, domain=p_data['domain'], p_data_json=json.dumps(p_data))
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/fix_rule', methods=['POST'])
def fix_rule():
    try:
        data = request.get_json()
        p_data = data.get('p_data', {})
        rule = data.get('rule', '')
        
        prompt = get_master_prompt(p_data, fix_rule=rule)
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "RE-DESIGN mode. Return full HTML for Stages 1-7. Ensure SQL logic is perfect."},
                {"role": "user", "content": prompt}
            ]
        )
        new_content = response.choices[0].message.content.replace("```html", "").replace("```", "").strip()
        return jsonify({"status": "success", "new_content": new_content})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/deploy_to_xampp', methods=['POST'])
def deploy_to_xampp():
    try:
        data = request.get_json()
        sql_script = data.get('sql_code', '')
        rules_list = data.get('business_rules', [])
        
        # --- 1. DB Adı Temizleme ---
        raw_name = data.get('domain', 'gen_db')
        tr_map = str.maketrans("ğĞüÜşŞİıöÖçÇ", "gGuUsSiIoOcC")
        clean_db_name = re.sub(r'[^a-zA-Z0-9_]', '_', raw_name.translate(tr_map)).lower()
        db_name = clean_db_name.strip('_') if clean_db_name.strip('_') else "gen_db"

        # --- 2. Bağlantı ---
        conn = mysql.connector.connect(host="localhost", user="root", passwd="")
        cursor = conn.cursor()
        
        # --- 3. Veritabanı Oluşturma ---
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
        cursor.execute(f"USE {db_name}")

        # --- 4. Tabloları Oluştur (Standart SQL) ---
        commands = sql_script.split(';')
        for command in commands:
            cmd = command.strip()
            # AI'nın oluşturduğu DELIMITER'lı triggerları atlıyoruz (Python ile biz ekleyeceğiz)
            if cmd and not any(x in cmd.upper() for x in ["DELIMITER", "$$"]):
                try:
                    cursor.execute(cmd)
                except Exception as db_err:
                    print(f"Komut atlandı: {db_err}")

        # --- 5. TRIGGER ENJEKSİYONU (YENİ EKLENEN KISIM) ---
        # Tablolar oluştuktan sonra garantili çalışan Python fonksiyonumuzu çağırıyoruz.
        inject_smart_triggers(cursor, db_name)

        # --- 6. Kuralları Kaydetme ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS _system_business_rules (
                id INT AUTO_INCREMENT PRIMARY KEY,
                rule_id VARCHAR(50),
                rule_description TEXT,
                rule_status VARCHAR(20) DEFAULT 'ACTIVE',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        try:
            cursor.execute("ALTER TABLE _system_business_rules ADD COLUMN rule_status VARCHAR(20) DEFAULT 'ACTIVE'")
        except:
            pass

        for rule in rules_list:
            r_id = rule.get('id', 'UNK')
            status = 'HISTORY' if 'GAP-LOG' in r_id else 'ACTIVE'
            
            cursor.execute(
                "INSERT INTO _system_business_rules (rule_id, rule_description, rule_status) VALUES (%s, %s, %s)",
                (r_id, rule.get('desc', ''), status)
            )

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"status": "success", "message": f"Veritabanı '{db_name}' ve Triggerlar başarıyla kuruldu!"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)