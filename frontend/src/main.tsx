import React, { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

type Project = { id: number; key: string; name: string; color?: string; todo_count: number; done_count: number; last_activity_at: string };
type Activity = { id: number; actor?: string; author?: string; type?: string; body?: string; created_at: string };
type Task = {
  id: number; title: string; description: string; status: "TODO" | "DONE"; priority: string;
  target_project: string; origin_project: string; assigned_agent: string | null; tags: string[];
  comments: Activity[]; events: Activity[]; updated_at: string;
};

const priorities = ["LOW", "NORMAL", "HIGH", "URGENT"];
const relative = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

function updatedAgo(value: string) {
  const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000);
  if (Math.abs(seconds) < 60) return relative.format(seconds, "second");
  if (Math.abs(seconds) < 3600) return relative.format(Math.round(seconds / 60), "minute");
  if (Math.abs(seconds) < 86400) return relative.format(Math.round(seconds / 3600), "hour");
  return relative.format(Math.round(seconds / 86400), "day");
}

function App() {
  const [token, setToken] = useState(localStorage.getItem("taskrelay-token") || "");
  const [projects, setProjects] = useState<Project[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [project, setProject] = useState(() => new URLSearchParams(location.search).get("project") || "");
  const [tag, setTag] = useState("");
  const [priority, setPriority] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Task | null>(null);
  const [creating, setCreating] = useState(false);
  const [quickTitle, setQuickTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [changed, setChanged] = useState<number[]>([]);
  const [error, setError] = useState("");
  const requestNumber = useRef(0);
  const knownUpdates = useRef(new Map<number, string>());
  const knownProject = useRef("");
  const changedTimer = useRef<number | undefined>(undefined);

  const request = async (path: string, init: RequestInit = {}) => {
    const response = await fetch(path, { ...init, headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...init.headers } });
    if (!response.ok) throw new Error((await response.json()).detail || response.statusText);
    return response.status === 204 ? null : response.json();
  };

  const refresh = async () => {
    if (!token) return;
    localStorage.setItem("taskrelay-token", token);
    const number = ++requestNumber.current;
    try {
      const nextProjects = await request("/api/projects");
      const nextTasks: Task[] = project ? await request(`/api/tasks?project=${encodeURIComponent(project)}&limit=200`) : [];
      if (number !== requestNumber.current) return;
      if (project) {
        const advanced = knownProject.current === project
          ? nextTasks.filter((item) => !knownUpdates.current.has(item.id) || knownUpdates.current.get(item.id)! < item.updated_at).map((item) => item.id)
          : [];
        knownUpdates.current = new Map(nextTasks.map((item) => [item.id, item.updated_at]));
        knownProject.current = project;
        if (advanced.length) {
          setChanged(advanced);
          window.clearTimeout(changedTimer.current);
          changedTimer.current = window.setTimeout(() => setChanged([]), 1800);
        }
      } else { knownUpdates.current.clear(); knownProject.current = ""; }
      setProjects(nextProjects); setTasks(nextTasks); setError("");
    } catch (reason) { if (number === requestNumber.current) setError(String(reason)); }
  };

  useEffect(() => { void refresh(); }, [token, project]);
  useEffect(() => {
    if (!token) return;
    const onFocus = () => void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    window.addEventListener("focus", onFocus);
    return () => { window.clearInterval(timer); window.removeEventListener("focus", onFocus); };
  }, [token, project]);
  useEffect(() => {
    const onPopState = () => setProject(new URLSearchParams(location.search).get("project") || "");
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const chooseProject = (key: string) => {
    history.pushState({ taskrelayProject: !!key }, "", key ? `${location.pathname}?project=${encodeURIComponent(key)}` : location.pathname);
    setProject(key); setSelected(null); setTag(""); setPriority(""); setQuery("");
  };
  const backToProjects = () => {
    if (history.state?.taskrelayProject) history.back();
    else chooseProject("");
  };
  const tags = useMemo(() => [...new Set(tasks.flatMap((task) => task.tags))].sort(), [tasks]);
  const visible = tasks.filter((task) => (!tag || task.tags.includes(tag)) && (!priority || task.priority === priority) && (!query || `${task.title} ${task.description}`.toLowerCase().includes(query.toLowerCase())));

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); if (!selected) return;
    const data = new FormData(event.currentTarget);
    const updated = await request(`/api/tasks/${selected.id}`, { method: "PATCH", body: JSON.stringify({ title: data.get("title"), description: data.get("description"), priority: data.get("priority"), tags: String(data.get("tags") || "").split(","), assigned_agent: data.get("assigned_agent") || null, target_project: data.get("target_project") }) });
    setSelected(updated); await refresh();
  };
  const complete = async () => {
    if (!selected || !summary.trim()) { setError("Completion summary is required."); return; }
    const updated = await request(`/api/tasks/${selected.id}/complete`, { method: "POST", body: JSON.stringify({ summary }) });
    setSelected(updated); setSummary(""); await refresh();
  };
  const reopen = async () => {
    if (!selected) return;
    const updated = await request(`/api/tasks/${selected.id}`, { method: "PATCH", body: JSON.stringify({ status: "TODO" }) });
    setSelected(updated); await refresh();
  };
  const quickAdd = async (event: FormEvent) => {
    event.preventDefault(); if (!project || !quickTitle.trim()) return;
    await request("/api/tasks", { method: "POST", body: JSON.stringify({ title: quickTitle, target_project: project, origin_project: project }) });
    setQuickTitle(""); await refresh();
  };
  const create = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    await request("/api/tasks", { method: "POST", body: JSON.stringify({ title: data.get("title"), target_project: data.get("target_project"), origin_project: data.get("target_project") }) });
    setCreating(false); await refresh();
  };

  if (!token) return <main className="login"><h1>TaskRelay</h1><p>Workspace bearer token</p><input aria-label="Workspace bearer token" type="password" onKeyDown={(event) => event.key === "Enter" && setToken(event.currentTarget.value)} autoFocus /></main>;

  return <main>
    <header><div><h1>TaskRelay</h1><small>{project ? projects.find((item) => item.key === project)?.name || project : "Projects"}</small></div><div><button onClick={() => setCreating(true)}>+ Task</button><button className="quiet" onClick={() => { localStorage.removeItem("taskrelay-token"); setToken(""); }}>Lock</button></div></header>
    {error && <p className="error">{error}</p>}
    {!project ? <section className="projects">{projects.map((item) => <button className="project-card" key={item.id} onClick={() => chooseProject(item.key)}><strong>{item.name}</strong><span>{item.todo_count} Todo · {item.done_count} Done</span><small>Updated {updatedAgo(item.last_activity_at)}</small></button>)}</section> : <>
      <nav><button className="quiet" onClick={backToProjects}>← Projects</button><select aria-label="Filter by tag" value={tag} onChange={(event) => setTag(event.target.value)}><option value="">All tags</option>{tags.map((item) => <option key={item}>{item}</option>)}</select><select aria-label="Filter by priority" value={priority} onChange={(event) => setPriority(event.target.value)}><option value="">All priorities</option>{priorities.map((item) => <option key={item}>{item}</option>)}</select><input aria-label="Search tasks" placeholder="Search…" value={query} onChange={(event) => setQuery(event.target.value)} /></nav>
      <form className="quick-add" onSubmit={quickAdd}><input aria-label="New task title" placeholder="Add a task…" value={quickTitle} onChange={(event) => setQuickTitle(event.target.value)} required maxLength={240} /><button>Add Todo</button></form>
      <section><h2>Todo <small>{visible.filter((item) => item.status === "TODO").length}</small></h2><div className="task-list">{visible.filter((item) => item.status === "TODO").map((item) => <button className={`task ${changed.includes(item.id) ? "changed" : ""}`} key={item.id} onClick={() => { setSelected(item); setSummary(""); }}><span className={`priority ${item.priority.toLowerCase()}`}>{item.priority}</span><strong>{item.title}</strong><small>Updated {updatedAgo(item.updated_at)}</small><span>{item.tags.map((name) => <em key={name}>{name}</em>)}</span></button>)}</div></section>
      <details><summary>Done ({visible.filter((item) => item.status === "DONE").length})</summary><div className="task-list">{visible.filter((item) => item.status === "DONE").map((item) => <button className={`task ${changed.includes(item.id) ? "changed" : ""}`} key={item.id} onClick={() => { setSelected(item); setSummary(""); }}><strong>{item.title}</strong><small>Updated {updatedAgo(item.updated_at)}</small></button>)}</div></details>
    </>}
    {selected && <aside className="drawer"><button aria-label="Close task" className="close" onClick={() => setSelected(null)}>×</button><h2>#{selected.id}</h2><form key={selected.id} onSubmit={save}><label>Title<input name="title" defaultValue={selected.title} required maxLength={240} /></label><label>Description<textarea name="description" defaultValue={selected.description} rows={6} /></label><label>Priority<select name="priority" defaultValue={selected.priority}>{priorities.map((item) => <option key={item}>{item}</option>)}</select></label><label>Tags<input name="tags" defaultValue={selected.tags.join(", ")} /></label><label>Assigned agent<input name="assigned_agent" defaultValue={selected.assigned_agent || ""} /></label><label>Target project<select name="target_project" defaultValue={selected.target_project}>{projects.map((item) => <option key={item.id} value={item.key}>{item.name}</option>)}</select></label><p>Origin: {selected.origin_project}</p><button>Save changes</button></form>{selected.status === "DONE" ? <button onClick={() => void reopen()}>Reopen as Todo</button> : <section className="complete"><label>Completion summary<textarea value={summary} onChange={(event) => setSummary(event.target.value)} required rows={3} /></label><button onClick={() => void complete()}>Complete</button></section>}<h3>Activity</h3>{[...selected.events, ...selected.comments].sort((a, b) => a.created_at.localeCompare(b.created_at)).map((item) => <p key={`${item.type || "comment"}-${item.id}`}><strong>{item.actor || item.author}</strong> {item.type || item.body}</p>)}</aside>}
    {creating && <div className="modal"><form onSubmit={create}><button type="button" className="close" onClick={() => setCreating(false)}>×</button><h2>New task</h2><label>Title<input name="title" required maxLength={240} /></label><label>Project<select name="target_project" required defaultValue={project}>{!project && <option value="">Choose…</option>}{projects.map((item) => <option key={item.id} value={item.key}>{item.name}</option>)}</select></label><button>Create Todo</button></form></div>}
  </main>;
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
