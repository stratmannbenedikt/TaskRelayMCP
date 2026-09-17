import { filterTasks } from '../shared/task-filters';
import { Task } from '../models';

describe('shared task filtering', () => {
  it('uses match-all tag identities and distinct recent/newest ordering', () => {
    const tasks = [task(1, '2026-01-01', '2026-01-03', [7, 8]), task(2, '2026-01-02', '2026-01-01', [7])];
    const base = { q: '', project: '', status: '', priority: '', assignment: 'all', tagIds: [7, 8], sort: 'newest' };
    expect(filterTasks(tasks, base).map(value => value.id)).toEqual([1]);
    expect(filterTasks(tasks, { ...base, tagIds: [], sort: 'recent' }).map(value => value.id)).toEqual([1, 2]);
  });
});

function task(id: number, created_at: string, updated_at: string, ids: number[]): Task { return { id, title: `Task ${id}`, description: '', status: 'TODO', priority: 'NORMAL', target_project: 'project', origin_project: 'project', creator: 'User', tags: ids.map(value => ({ id: value, project: 'project', name: `tag-${value}`, color: '#80643d', description: '', archived_at: null, usage_count: 0, creator: 'User', created_at: '', updated_at: '' })), comments: [], events: [], created_at, updated_at }; }
