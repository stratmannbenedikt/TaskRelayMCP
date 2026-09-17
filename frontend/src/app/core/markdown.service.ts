import { Injectable } from '@angular/core';
import MarkdownIt from 'markdown-it';

@Injectable({ providedIn: 'root' })
export class MarkdownService {
  private markdown = new MarkdownIt({ html: false, linkify: true });
  render(value: string, references: { id: number }[] = [], href = (id: string) => `/notes/${id}`) {
    return this.markdown.render(value.replace(/\[\[N-(\d+)(?:\|([^\]]+))?\]\]/g, (_, id, label) => references.some(note => note.id === Number(id)) ? `[${String(label || `N-${id}`).replace(/[\[\]]/g, '')}](${href(id)})` : `**Unresolved N-${id}**`));
  }
}
