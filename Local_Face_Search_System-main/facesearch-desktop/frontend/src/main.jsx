import React, {useEffect, useState} from "react";
import {createRoot} from "react-dom/client";
import "./style.css";

const API = "http://127.0.0.1:8765";

async function api(path, options={}) {
  const r = await fetch(`${API}${path}`, options);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Request failed");
  return data;
}

function App() {
  const [stats, setStats] = useState(null);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState("");
  const [results, setResults] = useState([]);
  const [threshold, setThreshold] = useState("0.45");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [connecting, setConnecting] = useState(false);

  const refresh = async () => {
    try { setStats(await api("/api/stats")); } catch (e) {}
  };
  useEffect(() => { refresh(); const t=setInterval(refresh,1500); return()=>clearInterval(t); }, []);

  const selectFolder = async () => {
    setError("");
    try {
      const path = window.desktop?.selectFolder ? await window.desktop.selectFolder() : window.prompt("Enter the full path of your photo folder:");
      if (!path) return;
      setConnecting(true);
      await api("/api/folder/connect", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({path})});
      await refresh();
    } catch(e){setError(e.message);} finally{setConnecting(false);}
  };

  const disconnect = async () => { try {await api("/api/folder/disconnect",{method:"POST"}); await refresh();} catch(e){setError(e.message);} };
  const rescan = async () => { try {await api("/api/folder/rescan",{method:"POST"}); await refresh();} catch(e){setError(e.message);} };
  const chooseFile = e => {const f=e.target.files?.[0]; if(!f)return; setFile(f);setPreview(URL.createObjectURL(f));setResults([]);setError("");};
  const search = async () => {
    if(!file)return setError("Choose a query photo first.");
    setBusy(true);setError("");setResults([]);
    const form=new FormData();form.append("file",file);
    try {const d=await api(`/api/search?top_k=20&threshold=${encodeURIComponent(threshold)}`,{method:"POST",body:form});setResults(d.results||[]);}catch(e){setError(e.message);}finally{setBusy(false);}
  };
  const openImage = async id => {try{await api(`/api/open-image/${id}`,{method:"POST"});}catch(e){setError(e.message);}};
  const openFolder = async id => {try{await api(`/api/open-folder/${id}`,{method:"POST"});}catch(e){setError(e.message);}};

  const root = stats?.root || "";
  const folderExists = stats?.folder_exists ?? false;
  const connected = !!root && folderExists;
  const offline = !!root && !folderExists;
  const idx = stats?.index_status || {};
  const indexDir = stats?.index_dir || "";
  const indexBytes = stats?.vector_storage_bytes || 0;
  const indexSize = indexBytes < 1024 * 1024
    ? `${(indexBytes / 1024).toFixed(1)} KB`
    : `${(indexBytes / (1024 * 1024)).toFixed(1)} MB`;

  return <main>
    <header>
      <div><div className="eyebrow">LOCAL • PRIVATE • AUTOMATIC</div><h1>FaceSearch</h1><p>Find people in your own photo collection without uploading the collection anywhere.</p></div>
      <div className="status"><i className={connected?"on":offline?"warn":"off"}></i>{connected?"Folder connected":offline?"Folder unavailable":"No folder connected"}</div>
    </header>

    <section className="library panel">
      <div className="library-main">
        <div className="eyebrow">PHOTO LIBRARY</div>
        <h2>{root || "Connect a photo folder"}</h2>
        <p>{offline ? "The saved folder is unavailable. Reconnect the drive or choose its new location." : connected ? "New, changed and deleted images are detected automatically." : "Choose a folder. Photos and face embeddings stay on this computer."}</p>
        <div className="actions"><button onClick={selectFolder} disabled={connecting}>{connecting?"Connecting…":offline?"Reconnect Folder":connected?"Change Folder":"Select Photo Folder"}</button>{connected&&<><button className="secondary" onClick={rescan}>Rescan</button><button className="secondary" onClick={disconnect}>Disconnect</button></>}</div>
      </div>
      <div className="metrics"><div><strong>{stats?.indexed_images??0}</strong><span>images indexed</span></div><div><strong>{stats?.indexed_faces??0}</strong><span>faces indexed</span></div><div><strong>{indexSize}</strong><span>vector index size</span></div><div><strong>{stats?.missing_images??0}</strong><span>missing</span></div></div>
      {root&&<div className="progressline"><span>{idx.running?`Indexing… ${idx.queued} queued`:(offline?"Storage unavailable":"Index is up to date")}</span><span className="path">Index: {indexDir}</span></div>}
    </section>

    <section className="panel searchbox"><div className="eyebrow">SEARCH</div><div className="searchrow"><label className="upload"><input type="file" accept="image/*" onChange={chooseFile}/>{preview?<img src={preview} alt="Query"/>:<span>＋<br/>Choose query photo</span>}</label><div className="controls"><label>Similarity threshold<input type="number" min="-1" max="1" step="0.01" value={threshold} onChange={e=>setThreshold(e.target.value)}/></label><button onClick={search} disabled={busy||!file||!connected}>{busy?"Searching…":"Search"}</button>{!connected&&<small>Connect an available photo folder first.</small>}<small>Similarity is a retrieval score, not an identity percentage. Search uses compact local embeddings; originals remain in their selected folder.</small></div></div></section>
    {error&&<div className="error">{error}</div>}
    <section><div className="head"><h2>Matches</h2><span>{results.length} results</span></div>{!results.length&&!busy?<div className="empty">Matching images will appear here.</div>:<div className="grid">{results.map((r,i)=><article className="card" key={`${r.vector_id}-${i}`}><img src={`${API}/api/image/${r.vector_id}`} alt={`Match ${i+1}`}/><div className="meta"><strong>#{i+1} · {r.similarity.toFixed(4)}</strong><span>{r.image_path}</span><div className="cardactions"><button onClick={()=>openImage(r.vector_id)}>Open Image</button><button className="secondary" onClick={()=>openFolder(r.vector_id)}>Open Folder</button></div></div></article>)}</div>}</section>
  </main>;
}
createRoot(document.getElementById("root")).render(<App/>);
