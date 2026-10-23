const DRAFT_SECTIONS = [
  ['summary', 'Summary'],
  ['timeline', 'Timeline of Events'],
  ['evidence_list', 'Evidence Submitted'],
  ['conclusion', 'Conclusion & Requested Action'],
];

export function renderCleanDraft(cleanDraft) {
  if (!cleanDraft || typeof cleanDraft !== 'object') return '';
  if (typeof cleanDraft.draft_text === 'string') return cleanDraft.draft_text;

  const lines = [
    `# Dispute Contest Rebuttal: ${cleanDraft.dispute_id || cleanDraft.case_id || ''}`,
    `**Case Reference**: ${cleanDraft.case_id || ''}`,
  ];

  for (const [key, title] of DRAFT_SECTIONS) {
    lines.push('', `## ${title}`);
    const sentences = Array.isArray(cleanDraft[key]) ? cleanDraft[key] : [];
    for (const item of sentences) {
      if (typeof item?.sentence !== 'string' || !item.sentence.trim()) continue;
      const citations = Array.isArray(item.cited_fact_ids)
        ? item.cited_fact_ids.filter((id) => typeof id === 'string' && id.trim())
        : [];
      lines.push(`- ${item.sentence}${citations.length ? ` ${citations.map((id) => `[${id}]`).join(' ')}` : ''}`);
    }
  }

  return lines.join('\n').trim();
}

export function renderDraftPreview(cleanDraft) {
  return renderCleanDraft(cleanDraft)
    .replace(/^# Dispute Contest Rebuttal:.*\n?/m, '')
    .replace(/^\*\*Case Reference\*\*:/gm, 'Case reference:')
    .replace(/^## (.+)$/gm, '$1')
    .replace(/^- /gm, '• ')
    .replace(/\s+\[fact_[^\]]+\]/g, '')
    .trim();
}
