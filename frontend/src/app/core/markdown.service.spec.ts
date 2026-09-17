import { MarkdownService } from './markdown.service';

describe('MarkdownService', () => {
  it('renders only resolved wiki links and never HTML', () => {
    const html = new MarkdownService().render('<script>x</script> [[N-2]] [[N-3]]', [{ id: 2 }]);
    expect(html).toContain('href="/notes/2"');
    expect(html).toContain('Unresolved N-3');
    expect(html).not.toContain('<script>');
  });
});
