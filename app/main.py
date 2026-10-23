import difflib, hashlib, json, os, re, shutil, tempfile
from dotenv import load_dotenv
load_dotenv()
from pathlib import Path
from fastapi import FastAPI, Depends, File, UploadFile, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import select
from .database import Base, engine, get_db, SessionLocal
from .models import Document, DocumentVersion, SectionNode, Selection, SelectionItem
from .schemas import SelectionIn, GenerationIn
from .parser import parse_text, extract_pdf
from .generator import generate_cases, load_store, save_store

Base.metadata.create_all(bind=engine)
app = FastAPI(title="TraceQA API", version="1.0.0", description="Versioned medical-document traceability and QA test generation.")
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(): return (FRONTEND / "index.html").read_text(encoding="utf-8")

def digest(text: str) -> str: return hashlib.sha256(re.sub(r'\s+', ' ', text).strip().encode()).hexdigest()

def node_dict(n: SectionNode):
    return {"id":n.id,"logical_key":n.logical_key,"heading":n.heading,"level":n.level,"body_text":n.body_text,"content_hash":n.content_hash,"change_status":n.change_status,"parent_id":n.parent_id,"order_index":n.order_index}

def _section_sort_key(node: SectionNode):
    """Sort numbered sibling sections by their printed section number, then source order."""
    match = re.match(r"^\s*(\d+(?:\.\d+)*)\b", node.heading)
    if match:
        parts = tuple(int(part) for part in match.group(1).split("."))
        return (0, parts, node.order_index)
    return (1, (), node.order_index)


def tree_dict(n: SectionNode):
    result = node_dict(n)
    result["children"] = [tree_dict(c) for c in sorted(n.children, key=_section_sort_key)]
    return result

def get_document(db: Session) -> Document | None:
    return db.scalar(select(Document).order_by(Document.id))

def ingest_text(db: Session, text: str, filename: str, title: str = "CardioTrack CT-200 Home Blood Pressure Monitor"):
    nodes = parse_text(text)
    doc = get_document(db)
    if doc is None:
        doc = Document(title=title, latest_version=0); db.add(doc); db.flush()
    old_version = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id==doc.id, DocumentVersion.version_number==doc.latest_version)) if doc.latest_version else None
    old_by_key = {n.logical_key:n for n in old_version.nodes} if old_version else {}
    version = DocumentVersion(document_id=doc.id, version_number=doc.latest_version+1, source_filename=filename)
    db.add(version); db.flush()
    created: list[SectionNode] = []
    for i, parsed in enumerate(nodes):
        prior = old_by_key.get(parsed.logical_key)
        if prior:
            status = "unchanged" if prior.content_hash == parsed.content_hash else "modified"
        else: status = "new"
        parent = created[parsed.parent_index] if parsed.parent_index is not None else None
        node = SectionNode(logical_key=parsed.logical_key, version_id=version.id, parent_id=parent.id if parent else None,
            heading=parsed.heading, level=parsed.level, body_text=parsed.body_text,
            content_hash=parsed.content_hash, order_index=i, change_status=status)
        db.add(node); db.flush(); created.append(node)
    # Prior nodes missing from this version are represented in diff API as removed.
    doc.latest_version = version.version_number
    db.commit(); db.refresh(version)
    return doc, version, created

@app.get("/api/health")
def health(): return {"status":"ok","service":"TraceQA"}

@app.get("/api/overview")
def overview(db: Session=Depends(get_db)):
    doc = get_document(db)
    if not doc: return {"document":None,"latest_version":0,"versions":0,"sections":0,"selections":0,"generations":len(load_store())}
    ver = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id==doc.id, DocumentVersion.version_number==doc.latest_version))
    return {"document":doc.title,"latest_version":doc.latest_version,"versions":len(doc.versions),"sections":len(ver.nodes) if ver else 0,
            "selections":db.query(Selection).count(),"generations":len(load_store()),"source_filename":ver.source_filename if ver else None}

@app.post("/api/ingest")
async def ingest(file: UploadFile=File(...), db: Session=Depends(get_db)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400,"Please upload a PDF file.")
    content = await file.read()
    if len(content) > 25 * 1024 * 1024: raise HTTPException(413,"PDF must be 25 MB or smaller.")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content); temp_path=tmp.name
    try:
        try: text, method = extract_pdf(temp_path)
        except ValueError as e: raise HTTPException(422,str(e))
        if len(text.strip()) < 30: raise HTTPException(422,"The PDF yielded too little text to build a reliable hierarchy.")
        doc, ver, nodes = ingest_text(db, text, file.filename)
        return {"message":"Document ingested","document_id":doc.id,"version":ver.version_number,"source_filename":file.filename,"extraction_method":method,"node_count":len(nodes),"warnings":["Heuristic heading detection requires manual review; verify the tree against the PDF."]}
    finally:
        try: os.unlink(temp_path)
        except OSError: pass

@app.post("/api/demo/seed")
def seed_demo(db: Session=Depends(get_db)):
    if get_document(db): return {"message":"A document already exists. Upload a PDF to create the next version.","latest_version":get_document(db).latest_version}
    text = '''CARDIOTRACK CT-200 HOME BLOOD PRESSURE MONITOR\nUser and Engineering Manual\n1 Introduction\nThe CT-200 is a home blood pressure monitor. Follow the instructions in this manual.\n2 Safety Information\n2.1 Intended Use\nThe device measures blood pressure and pulse rate for home use by adults.\n2.2 Warnings\nDo not use a damaged cuff. Stop measurement if severe discomfort occurs.\n3 Device Operation\n3.1 Power On\nPress the power button to initialize the monitor. The display should become active.\n3.2 Measurement\nFit the cuff as instructed and press Start. Remain still during measurement.\n3.3 Error Handling\nIf cuff fit is invalid, the monitor displays an error and measurement is not reported as successful.\n4 Maintenance\nClean the monitor with a soft dry cloth. Do not immerse the device in water.\n5 Technical Specifications\nThe monitor is intended for indoor use. Refer to the product label for electrical ratings.'''
    doc, ver, nodes = ingest_text(db,text,"demo_ct200_v1.txt")
    return {"message":"Demo manual created","version":ver.version_number,"node_count":len(nodes),"note":"Demo text is illustrative, not the assignment's actual PDF."}

@app.get("/api/versions")
def versions(db: Session=Depends(get_db)):
    doc=get_document(db)
    if not doc: return {"versions":[],"latest_version":0}
    return {"latest_version":doc.latest_version,"versions":[{"id":v.id,"version":v.version_number,"source_filename":v.source_filename,"created_at":v.created_at.isoformat()} for v in sorted(doc.versions,key=lambda x:x.version_number)]}

@app.get("/api/sections")
def sections(version: int|None=Query(default=None), db: Session=Depends(get_db)):
    doc=get_document(db)
    if not doc: return {"version":0,"sections":[]}
    version=version or doc.latest_version
    ver=db.scalar(select(DocumentVersion).where(DocumentVersion.document_id==doc.id,DocumentVersion.version_number==version))
    if not ver: raise HTTPException(404,"Document version not found")
    roots=[n for n in ver.nodes if n.parent_id is None]
    return {"version":version,"sections":[tree_dict(n) for n in sorted(roots,key=_section_sort_key)]}

@app.get("/api/nodes/{node_id}")
def get_node(node_id: int, db: Session=Depends(get_db)):
    n=db.get(SectionNode,node_id)
    if not n: raise HTTPException(404,"Node not found")
    out=node_dict(n); out["children"]=[node_dict(c) for c in sorted(n.children, key=_section_sort_key)]
    out["version"]=n.version.version_number
    return out

@app.get("/api/search")
def search(q: str=Query(min_length=1), version: int|None=None, db: Session=Depends(get_db)):
    doc=get_document(db)
    if not doc: return {"query":q,"results":[]}
    version=version or doc.latest_version
    ver=db.scalar(select(DocumentVersion).where(DocumentVersion.document_id==doc.id,DocumentVersion.version_number==version))
    if not ver: raise HTTPException(404,"Document version not found")
    needle=q.casefold()
    results=[node_dict(n) for n in ver.nodes if needle in n.heading.casefold() or needle in n.body_text.casefold()]
    return {"query":q,"version":version,"results":results[:100]}

@app.get("/api/nodes/{node_id}/diff")
def node_diff(node_id: int, from_version: int|None=None, to_version: int|None=None, db: Session=Depends(get_db)):
    n=db.get(SectionNode,node_id)
    if not n: raise HTTPException(404,"Node not found")
    doc=n.version.document; from_version=from_version or n.version.version_number; to_version=to_version or doc.latest_version
    versions={v.version_number:v for v in doc.versions}
    if from_version not in versions or to_version not in versions: raise HTTPException(404,"Version not found")
    source=next((x for x in versions[from_version].nodes if x.logical_key==n.logical_key),None)
    target=next((x for x in versions[to_version].nodes if x.logical_key==n.logical_key),None)
    if not source or not target:
        status = "removed" if source and not target else "added"
        return {"logical_key":n.logical_key,"heading":n.heading,"from_version":from_version,"to_version":to_version,"changed":True,"status":status,"summary":f"Section {status} between v{from_version} and v{to_version}.","before_text":source.body_text if source else None,"after_text":target.body_text if target else None,"diff":[]}
    changed=source.content_hash!=target.content_hash
    diff=list(difflib.unified_diff(source.body_text.splitlines(),target.body_text.splitlines(),fromfile=f"v{from_version}",tofile=f"v{to_version}",lineterm="")) if changed else []
    removed_lines=sum(1 for line in diff if line.startswith('-') and not line.startswith('---'))
    added_lines=sum(1 for line in diff if line.startswith('+') and not line.startswith('+++'))
    summary=(f"Section content changed: {removed_lines} line(s) removed or replaced and {added_lines} line(s) added or replaced." if changed else f"No content change detected for this section between v{from_version} and v{to_version}.")
    return {"logical_key":n.logical_key,"heading":target.heading,"from_version":from_version,"to_version":to_version,"changed":changed,"status":"modified" if changed else "unchanged","summary":summary,"before_text":source.body_text,"after_text":target.body_text,"removed_lines":removed_lines,"added_lines":added_lines,"diff":diff[:120]}

@app.post("/api/selections")
def create_selection(payload: SelectionIn, db: Session=Depends(get_db)):
    nodes=[]
    for node_id in payload.node_ids:
        n=db.get(SectionNode,node_id)
        if not n: raise HTTPException(404,f"Node {node_id} not found")
        nodes.append(n)
    versions={n.version.version_number for n in nodes}
    if len(versions)>1: raise HTTPException(400,"All selected nodes must belong to the same document version.")
    if payload.version is not None and versions!={payload.version}: raise HTTPException(400,"Selected node IDs do not belong to the requested version.")
    sel=Selection(name=payload.name); db.add(sel); db.flush()
    for n in nodes:
        db.add(SelectionItem(selection_id=sel.id,node_id=n.id,version_id=n.version_id,content_hash_snapshot=n.content_hash,heading_snapshot=n.heading,text_snapshot=n.body_text))
    db.commit(); db.refresh(sel)
    return {"id":sel.id,"name":sel.name,"version":next(iter(versions)),"items":[{"node_id":i.node_id,"version":i.version_id,"heading":i.heading_snapshot,"content_hash":i.content_hash_snapshot} for i in sel.items]}

@app.get("/api/selections/{selection_id}")
def get_selection(selection_id: int, db: Session=Depends(get_db)):
    sel=db.get(Selection,selection_id)
    if not sel: raise HTTPException(404,"Selection not found")
    return {"id":sel.id,"name":sel.name,"items":[{"node_id":i.node_id,"version_id":i.version_id,"version":db.get(DocumentVersion,i.version_id).version_number,"heading":i.heading_snapshot,"text":i.text_snapshot,"content_hash":i.content_hash_snapshot} for i in sel.items]}

@app.post("/api/generations")
async def create_generation(payload: GenerationIn, db: Session=Depends(get_db)):
    sel=db.get(Selection,payload.selection_id)
    if not sel: raise HTTPException(404,"Selection not found")
    store=load_store()
    if not payload.force_new:
        existing=next((g for g in reversed(store) if g["selection_id"]==sel.id),None)
        if existing: return {**existing,"deduplicated":True}
    citations=[]
    for i in sel.items:
        citations.append({"node_id":i.node_id,"version":db.get(DocumentVersion,i.version_id).version_number,"heading":i.heading_snapshot,"text":i.text_snapshot,"content_hash":i.content_hash_snapshot})
    cases, model=await generate_cases(citations)
    record={"id":max([g.get("id",0) for g in store],default=0)+1,"selection_id":sel.id,"selection_name":sel.name,"source_nodes":[{"node_id":c["node_id"],"version":c["version"],"heading":c["heading"],"content_hash":c["content_hash"]} for c in citations],"test_cases":cases,"model":model,"created_at":__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),"deduplicated":False}
    store.append(record); save_store(store)
    return record

@app.get("/api/generations")
def list_generations(selection_id: int|None=None, node_id: int|None=None, db: Session=Depends(get_db)):
    store=load_store(); doc=get_document(db); latest=doc.latest_version if doc else 0
    if selection_id is not None: store=[g for g in store if g["selection_id"]==selection_id]
    if node_id is not None: store=[g for g in store if any(n["node_id"]==node_id for n in g["source_nodes"])]
    current_nodes={n.logical_key:n for n in (db.scalar(select(DocumentVersion).where(DocumentVersion.document_id==doc.id,DocumentVersion.version_number==latest)).nodes if doc and latest else [])}
    for g in store:
        statuses=[]
        for src in g["source_nodes"]:
            original=db.get(SectionNode,src["node_id"])
            current=current_nodes.get(original.logical_key) if original else None
            if not current: statuses.append({"node_id":src["node_id"],"status":"removed","current_hash":None})
            elif current.content_hash != src["content_hash"]: statuses.append({"node_id":src["node_id"],"status":"modified","current_hash":current.content_hash})
            else: statuses.append({"node_id":src["node_id"],"status":"current","current_hash":current.content_hash})
        g["staleness"]={"is_stale":any(s["status"]!="current" for s in statuses),"latest_version":latest,"nodes":statuses,"note":"Hash-based detection flags any selected heading/body change equally; it does not assess clinical significance."}
    return {"count":len(store),"generations":list(reversed(store))}

@app.get("/api/generations/{generation_id}")
def get_generation(generation_id: int, db: Session=Depends(get_db)):
    result=list_generations(selection_id=None,node_id=None,db=db)
    gen=next((g for g in result["generations"] if g["id"]==generation_id),None)
    if not gen: raise HTTPException(404,"Generation not found")
    return gen


@app.post("/api/traceability/recheck")
def recheck_traceability(db: Session=Depends(get_db)):
    """Recompute each saved generation against the latest document version."""
    result = list_generations(selection_id=None, node_id=None, db=db)
    generations = result["generations"]
    stale = [g for g in generations if g.get("staleness", {}).get("is_stale")]
    return {"message": "Traceability statuses recalculated.", "latest_version": max([g.get("staleness", {}).get("latest_version", 0) for g in generations], default=(get_document(db).latest_version if get_document(db) else 0)), "generations_reviewed": len(generations), "test_cases_tracked": sum(len(g.get("test_cases", [])) for g in generations), "needing_review": len(stale), "generations": generations}
