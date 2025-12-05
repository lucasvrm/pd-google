from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models

def seed_data():
    db = SessionLocal()

    # 1. Clear existing templates (to avoid duplicates if run multiple times)
    db.query(models.DriveStructureNode).delete()
    db.query(models.DriveStructureTemplate).delete()

    # Clear Mock Supabase Data (only for local dev, be careful in prod!)
    # We assume this script is for dev/setup only.
    if "sqlite" in str(engine.url):
        print("Clearing mock Supabase data...")
        db.query(models.Deal).delete()
        db.query(models.Lead).delete()
        db.query(models.Company).delete()

    # 2. Seed Mock Supabase Data (Companies, Leads, Deals)
    if "sqlite" in str(engine.url):
        print("Seeding Mock Supabase Data...")

        # Company
        company1 = models.Company(id="comp-123", name="Arie Properties SPE Ltda", fantasy_name="Arie Properties")
        db.add(company1)

        # Lead
        lead1 = models.Lead(id="lead-001", title="Arie - Terreno Vila Olímpia", company_id="comp-123")
        db.add(lead1)

        # Deal
        deal1 = models.Deal(id="deal-001", title="Arie - Gaya Vila Olímpia", company_id="comp-123")
        db.add(deal1)

        db.commit()

    # 3. Seed Drive Templates
    print("Seeding Drive Templates...")

    # --- TEMPLATE: LEAD ---
    lead_template = models.DriveStructureTemplate(name="Default Lead Template", entity_type="lead", active=True)
    db.add(lead_template)
    db.commit()

    lead_nodes = [
        "00. Administração do Lead",
        "01. Originação & Materiais",
        "02. Ativo / Terreno (Básico)",
        "03. Empreendimento & Viabilidade (Preliminar)",
        "04. Partes & KYC (Básico)",
        "05. Decisão Interna"
    ]

    for i, name in enumerate(lead_nodes):
        node = models.DriveStructureNode(template_id=lead_template.id, name=name, order=i)
        db.add(node)

    # --- TEMPLATE: DEAL ---
    deal_template = models.DriveStructureTemplate(name="Default Deal Template", entity_type="deal", active=True)
    db.add(deal_template)
    db.commit()

    deal_nodes = [
        "00. Administração do Deal",
        "01. Originação & Mandato",
        "02. Ativo / Terreno & Garantias",
        "03. Empreendimento & Projeto",
        "04. Comercial",
        "05. Financeiro & Modelagem",
        "06. Partes & KYC",
        "07. Jurídico & Estruturação",
        "08. Operação & Monitoring"
    ]

    # Map subfolders (simple 1-level for now in seeding, logic will handle deep creation if needed)
    # The requirement asks for specific subfolders.
    # Current TemplateService logic is flat (1 level deep).
    # We will seed the top level folders first.
    # Complex sub-structures (e.g. 02.01, 02.02) can be added here if we update TemplateService
    # to support recursion, or we just stick to the main folders as the requirement says "Subpastas (podem ser criadas já no template ou sob demanda)".
    # The user listed detailed subfolders. Let's try to add them flattened or update service later.
    # For now, I will add the main folders to ensure the structure exists.

    for i, name in enumerate(deal_nodes):
        node = models.DriveStructureNode(template_id=deal_template.id, name=name, order=i)
        db.add(node)

        # Add subfolders for "02. Ativo / Terreno & Garantias"
        if name.startswith("02"):
            sub_nodes = [
                "02.01 Matrículas & RI",
                "02.02 Escrituras / C&V Terreno",
                "02.03 Alvarás & Licenças",
                "02.04 Colateral Adicional",
                "02.05 Seguros & Apólices"
            ]
            # Since current Node model supports parent_id, we can technically seed them.
            # But TemplateService needs to be recursive.
            # I'll create them as children in DB, and will update TemplateService to recurse.
            # Wait, `node` is not committed yet so it has no ID.
            db.commit() # Commit to get ID
            db.refresh(node)
            for j, sub in enumerate(sub_nodes):
                sub_node = models.DriveStructureNode(template_id=deal_template.id, name=sub, parent_id=node.id, order=j)
                db.add(sub_node)

        # Add subfolders for "03. Empreendimento & Projeto"
        if name.startswith("03"):
            sub_nodes = ["03.01 Plantas & Projetos", "03.02 Memoriais & Quadros de Áreas", "03.03 Pesquisas de Mercado", "03.04 Books & Teasers"]
            db.commit(); db.refresh(node)
            for j, sub in enumerate(sub_nodes):
                db.add(models.DriveStructureNode(template_id=deal_template.id, name=sub, parent_id=node.id, order=j))

        # Add subfolders for "04. Comercial"
        if name.startswith("04"):
            sub_nodes = ["04.01 Tabelas de Vendas", "04.02 Contratos C&V Clientes", "04.03 Recebíveis & Borderôs"]
            db.commit(); db.refresh(node)
            for j, sub in enumerate(sub_nodes):
                db.add(models.DriveStructureNode(template_id=deal_template.id, name=sub, parent_id=node.id, order=j))

        # Add subfolders for "05. Financeiro"
        if name.startswith("05"):
            sub_nodes = ["05.01 Viabilidades", "05.02 Fluxos de Caixa", "05.03 Cronogramas Físico-Financeiros", "05.04 Planilhas KOA & Modelos"]
            db.commit(); db.refresh(node)
            for j, sub in enumerate(sub_nodes):
                db.add(models.DriveStructureNode(template_id=deal_template.id, name=sub, parent_id=node.id, order=j))

        # Add subfolders for "06. Partes & KYC"
        if name.startswith("06"):
            # Note: User mentioned dynamic folders for specific partners here. We just seed the categories.
            sub_nodes = ["06.01 Sócios PF", "06.02 PJs"]
            db.commit(); db.refresh(node)
            for j, sub in enumerate(sub_nodes):
                db.add(models.DriveStructureNode(template_id=deal_template.id, name=sub, parent_id=node.id, order=j))

        # Add subfolders for "07. Jurídico"
        if name.startswith("07"):
            sub_nodes = ["07.01 DD Jurídica", "07.02 Contratos Estruturais (SCPs, crédito, etc.)"]
            db.commit(); db.refresh(node)
            for j, sub in enumerate(sub_nodes):
                db.add(models.DriveStructureNode(template_id=deal_template.id, name=sub, parent_id=node.id, order=j))

        # Add subfolders for "08. Operação"
        if name.startswith("08"):
            sub_nodes = ["08.01 Relatórios Operacionais", "08.02 Recebíveis / Cash Flow Realizado", "08.03 Comunicação Recorrente"]
            db.commit(); db.refresh(node)
            for j, sub in enumerate(sub_nodes):
                db.add(models.DriveStructureNode(template_id=deal_template.id, name=sub, parent_id=node.id, order=j))


    # --- TEMPLATE: COMPANY (CLIENTE) ---
    company_template = models.DriveStructureTemplate(name="Default Company Template", entity_type="company", active=True)
    db.add(company_template)
    db.commit()

    company_nodes = [
        "01. Leads",
        "02. Deals",
        "03. Documentos Gerais",
        "90. Compartilhamento Externo",
        "99. Arquivo / Encerrados"
    ]

    for i, name in enumerate(company_nodes):
        node = models.DriveStructureNode(template_id=company_template.id, name=name, order=i)
        db.add(node)

        # Subfolders for "03. Documentos Gerais"
        if name.startswith("03"):
            sub_nodes = ["03.01 Dossiê Sócios PF", "03.02 Dossiê PJs", "03.03 Modelos / Planilhas KOA"]
            db.commit(); db.refresh(node)
            for j, sub in enumerate(sub_nodes):
                db.add(models.DriveStructureNode(template_id=company_template.id, name=sub, parent_id=node.id, order=j))

    db.commit()
    db.close()
    print("Seeding complete.")

if __name__ == "__main__":
    seed_data()
