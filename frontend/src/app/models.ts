export interface User { id: number; username: string; display_name: string; active: boolean; is_admin: boolean; must_change_password: boolean; }
export interface ProjectOut { id: number; key: string; name: string; description: string; color: string | null; archived: boolean; role: 'OWNER' | 'MEMBER' | null; tasks_enabled: boolean; notes_enabled: boolean; created_at: string; }
export interface ProjectTaskPreview { id: number; title: string; priority: string; assignee: string | null; updated_at: string; }
export interface ProjectRecentNote { id: number; title: string; updated_at: string; updater: string | null; folder_path: string | null; }
export interface ProjectActivity { action: string; object_type: 'TASK' | 'NOTE'; object_id: number; object_title: string; actor: string | null; created_at: string; }
export interface Project { id: number; key: string; name: string; description: string; color?: string | null; archived: boolean; role?: 'OWNER' | 'MEMBER'; tasks_enabled: boolean; notes_enabled: boolean; created_at: string; todo_count: number; done_count: number; note_count: number; last_activity_at: string; todo_preview: ProjectTaskPreview[]; recent_note: ProjectRecentNote | null; latest_activity: ProjectActivity | null; }
export interface Person { username: string; display_name: string; }
export interface Member extends Person { role: 'OWNER' | 'MEMBER'; }
export interface TaskEvent { id: number; actor: string; channel?: 'WEB' | 'MCP'; mcp_key?: string; type: string; }
export interface Tag { id: number; project: string; name: string; color: string; description: string; archived_at: string | null; usage_count: number; creator: string | null; created_at: string; updated_at: string; }
export interface TagProposal { id: number; project: string; name: string; color: string; description: string; status: string; proposed_by: string | null; mcp_key: string | null; created_at: string; expires_at: string; decided_by: string | null; decided_at: string | null; resolved_tag_id: number | null; task_ids: number[]; }
export interface Task { id: number; title: string; description: string; status: 'TODO' | 'DONE'; priority: string; target_project: string; origin_project: string; creator: string; assignee?: string | null; completer?: string | null; tags: Tag[]; comments: Record<string, unknown>[]; events: TaskEvent[]; created_at: string; updated_at: string; completed_at?: string | null; }
export interface McpKey { id: number; name: string; created_at: string; revoked_at?: string; }
export interface NoteFolder { id: number; project: string; parent_id: number | null; name: string; creator: string | null; created_at: string; }
export interface NoteReference { id: number; title: string; }
export interface Note { id: number; project: string; folder_id: number | null; title: string; markdown: string; version: number; creator: string | null; updater: string | null; created_at: string; updated_at: string; archived_at: string | null; references?: NoteReference[]; backlinks?: NoteReference[]; }
export interface NoteRevision { version: number; title: string; markdown: string; folder_id: number | null; archived_at: string | null; editor: string; created_at: string; }
