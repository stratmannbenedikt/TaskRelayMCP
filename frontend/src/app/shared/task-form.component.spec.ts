import { taskForm, TaskFormComponent } from './task-form.component';

describe('TaskFormComponent', () => {
  it('does not offer implicit creation, and creates/selects only a valid unmatched slug', () => {
    const component = new TaskFormComponent(); component.form = taskForm(); component.search.setValue('not valid'); expect(component.newName).toBe(''); component.search.setValue('new-tag'); expect(component.newName).toBe('new-tag');
  });
  it('creates and selects a tag without changing the parent task draft', async () => {
    const component = new TaskFormComponent(); component.form = taskForm(); component.form.controls.title.setValue('Draft'); component.form.controls.description.setValue('Keep this'); component.search.setValue('new-tag'); component.tagCreate.subscribe(request => request.resolve({ id: 9 } as never));
    await component.createTag();
    expect(component.form.getRawValue()).toMatchObject({ title: 'Draft', description: 'Keep this', tag_ids: [9] });
  });
});
