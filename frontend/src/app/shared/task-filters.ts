import { Task } from '../models';

export interface TaskFilter { q: string; project?: string; status: string; priority: string; assignment: string; tagIds: number[]; sort: string; }

export const defaultTaskFilter = (project = ''): TaskFilter => ({ q: '', project, status: 'TODO', priority: '', assignment: 'all', tagIds: [], sort: 'priority' });

export function filterTasks(tasks: Task[], filter: TaskFilter, displayName?: string) {
  const priorities = ['URGENT', 'HIGH', 'NORMAL', 'LOW'];
  const query = filter.q.toLowerCase();
  return tasks.filter(task =>
    (!filter.project || task.target_project === filter.project) && (!filter.status || task.status === filter.status) &&
    (!filter.priority || task.priority === filter.priority) && filter.tagIds.every(id => task.tags.some(tag => tag.id === id)) &&
    (!query || `${task.title} ${task.description}`.toLowerCase().includes(query)) &&
    (filter.assignment === 'all' || (filter.assignment === 'mine' ? task.assignee === displayName : !task.assignee)),
  ).sort((a, b) => filter.sort === 'priority' ? priorities.indexOf(a.priority) - priorities.indexOf(b.priority) || +new Date(b.updated_at) - +new Date(a.updated_at) : filter.sort === 'oldest' ? +new Date(a.created_at) - +new Date(b.created_at) : filter.sort === 'project' ? a.target_project.localeCompare(b.target_project) : filter.sort === 'newest' ? +new Date(b.created_at) - +new Date(a.created_at) : +new Date(b.updated_at) - +new Date(a.updated_at));
}
