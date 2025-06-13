from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.background import BackgroundScheduler
from vector_store import rebuild_qdrant, search_docs

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
async def startup_event():
    # Build vector store on first startup
    rebuild_qdrant()
    # Update every 24 hours
    scheduler = BackgroundScheduler()
    scheduler.add_job(rebuild_qdrant, "interval", hours=24)
    scheduler.start()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/query", response_class=HTMLResponse)
async def query(request: Request, user_query: str = Form(...)):
    results = search_docs(user_query)

    formatted_results = []
    for i, (text, score) in enumerate(results):
        snippet = text[:500] + ("..." if len(text) > 500 else "")
        formatted_results.append({
            "index": i + 1,
            "score": f"{score:.4f}",
            "snippet": snippet
        })

    return templates.TemplateResponse("index.html", {
        "request": request,
        "query": user_query,
        "results": formatted_results
    })

@app.get("/search")
def search(q: str = Query(..., description="Enter your question")):
    # Implementation of search function
    pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)