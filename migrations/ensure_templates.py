from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def ensure_templates():
    """
    Idempotent script to ensure default templates exist in the database.
    Does NOT delete existing templates. Only adds if missing.
    """
    db = SessionLocal()
    try:
        logger.info("Checking Drive Templates...")

        # --- LEAD TEMPLATE ---
        lead_tmpl = db.query(models.DriveStructureTemplate).filter_by(entity_type="lead", active=True).first()
        if not lead_tmpl:
            logger.info("Creating Default Lead Template...")
            lead_tmpl = models.DriveStructureTemplate(name="Default Lead Template", entity_type="lead", active=True)
            db.add(lead_tmpl)
            db.commit() # Commit to get ID
            db.refresh(lead_tmpl)

            nodes = [
                "00. Administração do Lead",
                "01. Originação & Materiais",
                "02. Ativo / Terreno (Básico)",
                "03. Empreendimento & Viabilidade (Preliminar)",
                "04. Partes & KYC (Básico)",
                "05. Decisão Interna"
            ]
            for i, name in enumerate(nodes):
                node = models.DriveStructureNode(template_id=lead_tmpl.id, name=name, order=i)
                db.add(node)
            db.commit()
            logger.info("Lead Template created.")
        else:
            logger.info("Lead Template already exists.")

        # --- DEAL TEMPLATE ---
        deal_tmpl = db.query(models.DriveStructureTemplate).filter_by(entity_type="deal", active=True).first()
        if not deal_tmpl:
            logger.info("Creating Default Deal Template...")
            deal_tmpl = models.DriveStructureTemplate(name="Default Deal Template", entity_type="deal", active=True)
            db.add(deal_tmpl)
            db.commit()
            db.refresh(deal_tmpl)

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
            for i, name in enumerate(deal_nodes):
                node = models.DriveStructureNode(template_id=deal_tmpl.id, name=name, order=i)
                db.add(node)
                # Note: Subfolders are skipped in this ensure script for simplicity/safely,
                # assuming if template is missing we just want base structure.
                # A full restore should use a more complex script if subfolders are critical for initial creation.
            db.commit()
            logger.info("Deal Template created.")
        else:
            logger.info("Deal Template already exists.")

        # --- COMPANY TEMPLATE ---
        comp_tmpl = db.query(models.DriveStructureTemplate).filter_by(entity_type="company", active=True).first()
        if not comp_tmpl:
            logger.info("Creating Default Company Template...")
            comp_tmpl = models.DriveStructureTemplate(name="Default Company Template", entity_type="company", active=True)
            db.add(comp_tmpl)
            db.commit()
            db.refresh(comp_tmpl)

            comp_nodes = [
                "01. Leads",
                "02. Deals",
                "03. Documentos Gerais",
                "90. Compartilhamento Externo",
                "99. Arquivo / Encerrados"
            ]
            for i, name in enumerate(comp_nodes):
                node = models.DriveStructureNode(template_id=comp_tmpl.id, name=name, order=i)
                db.add(node)
            db.commit()
            logger.info("Company Template created.")
        else:
            logger.info("Company Template already exists.")

    except Exception as e:
        logger.error(f"Error ensuring templates: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    ensure_templates()
