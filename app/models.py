from datetime import datetime, timezone
from sqlalchemy import String, Integer, Text, ForeignKey, DateTime, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

def utcnow(): return datetime.now(timezone.utc)

class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300), default="CT-200 Manual")
    latest_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    versions: Mapped[list["DocumentVersion"]] = relationship(back_populates="document", cascade="all, delete-orphan")

class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_number"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    source_filename: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    document: Mapped[Document] = relationship(back_populates="versions")
    nodes: Mapped[list["SectionNode"]] = relationship(back_populates="version", cascade="all, delete-orphan")

class SectionNode(Base):
    __tablename__ = "section_nodes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    logical_key: Mapped[str] = mapped_column(String(100), index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("section_nodes.id"), nullable=True, index=True)
    heading: Mapped[str] = mapped_column(String(1000), default="Untitled section")
    level: Mapped[int] = mapped_column(Integer, default=1)
    body_text: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    change_status: Mapped[str] = mapped_column(String(30), default="new")
    version: Mapped[DocumentVersion] = relationship(back_populates="nodes")
    parent: Mapped["SectionNode | None"] = relationship(remote_side="SectionNode.id", back_populates="children")
    children: Mapped[list["SectionNode"]] = relationship(back_populates="parent", cascade="all, delete-orphan", order_by="SectionNode.order_index")

class Selection(Base):
    __tablename__ = "selections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(250))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    items: Mapped[list["SelectionItem"]] = relationship(back_populates="selection", cascade="all, delete-orphan")

class SelectionItem(Base):
    __tablename__ = "selection_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    selection_id: Mapped[int] = mapped_column(ForeignKey("selections.id"), index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("section_nodes.id"), index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id"), index=True)
    content_hash_snapshot: Mapped[str] = mapped_column(String(64))
    heading_snapshot: Mapped[str] = mapped_column(String(1000))
    text_snapshot: Mapped[str] = mapped_column(Text)
    selection: Mapped[Selection] = relationship(back_populates="items")
