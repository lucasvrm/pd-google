"""
Cria templates de estrutura padrão para:
- lead
- company
- contact
- deal
"""

from database import SessionLocal
from models import DriveStructureTemplate, DriveStructureNode

db = SessionLocal()


def create_template(entity_type: str, folders: list[str]):
    template = DriveStructureTemplate(
        name=f"Default {entity_type.capitalize()} Template",
        entity_type=entity_type,
        active=True,
    )
    db.add(template)
    db.commit()

    for i, folder in enumerate(folders):
        node = DriveStructureNode(
            template_id=template.id,
            name=folder,
            order=i,
            parent_id=None,
        )
        db.add(node)

    db.commit()


# Executar apenas uma vez
print("Seeding templates...")

create_template("lead", ["Documentos", "Contratos", "Propostas"])
create_template("company", ["Contratos", "Financeiro", "Documentos"])
create_template("contact", ["Documentos"])
create_template("deal", ["Propostas", "Contratos", "Notas"])

print("Done.")
