from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models

def seed_db():
    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # 1. Check if templates exist
    existing = db.query(models.DriveStructureTemplate).filter_by(entity_type="client").first()
    if not existing:
        print("Seeding Client Template...")
        template = models.DriveStructureTemplate(name="Standard Client", entity_type="client")
        db.add(template)
        db.commit()
        db.refresh(template)

        # Nodes:
        # Client Root
        #   |-- Contracts
        #   |-- Proposals
        #   |-- Briefings

        n1 = models.DriveStructureNode(template_id=template.id, name="Contracts", order=1)
        n2 = models.DriveStructureNode(template_id=template.id, name="Proposals", order=2)
        n3 = models.DriveStructureNode(template_id=template.id, name="Briefings", order=3)

        db.add_all([n1, n2, n3])
        db.commit()
    else:
        print("Client Template already exists.")

    db.close()

if __name__ == "__main__":
    seed_db()
