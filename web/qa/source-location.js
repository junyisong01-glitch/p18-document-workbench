/* Display only: never alters source identities, permissions, or preview mappings. */
(function (root) {
  function format(doc, chunk, meta) {
    const pdf = doc.ext === '.pdf';
    const word = doc.ext === '.docx' || doc.ext === '.doc';
    const clean = value => typeof value === 'string' ? value.replace(/\s+/g, ' ').trim() : '';
    const section = clean(chunk.section);
    const sources = Array.isArray(chunk.sources) ? chunk.sources : [];
    const count = meta?.pages;
    const validPage = value => Number.isInteger(value) && value > 0 && Number.isInteger(count) && value <= count;
    const unique = values => [...new Set(values)];
    const pieces = [pdf ? 'PDF' : word ? 'Word' : '文档'];
    if (section) pieces.push(section);
    // Word location labels may include the section again. Extract structural
    // positions only; a label containing "第 N 页" is not a page mapping.
    if (word) {
      const labels = sources.flatMap(source => {
        const block = doc.result?.blocks?.find(item => item.id === source.block_id);
        return (clean(block?.label || source.label).match(/(?:段落|表格)\s*\d+/g) || []).map(label => label.replace(/(段落|表格)\s*(\d+)/, '$1 $2'));
      });
      const locations = unique(labels);
      if (locations.length) pieces.push(locations.join('、'));
      else if (!section) pieces.push('文档级来源');
    }
    const mappings = sources.map(source => {
      if (pdf) return source.page;
      if (!word) return null;
      return source.preview_pages?.original ?? doc.result?.blocks?.find(item => item.id === source.block_id)?.preview_pages?.original;
    });
    const pages = unique(mappings.filter(validPage)).sort((a, b) => a - b);
    if (pages.length) {
      pieces.push((pdf ? '物理第 ' : '系统转换预览第 ') + pages.join('、') + ' 页');
      if (mappings.some(page => !validPage(page))) pieces.push(pdf ? '部分位置未确定物理页码' : '部分位置暂无法确定预览页');
    } else if (pdf || word) {
      pieces.push(pdf ? '未确定物理页码' : '暂无法确定对应预览页');
    } else if (!section) pieces.push('文档级来源');
    return {text: unique(pieces).join(' · '), pages};
  }
  root.P18SourceLocation = {format};
})(typeof window === 'undefined' ? module.exports : window);
