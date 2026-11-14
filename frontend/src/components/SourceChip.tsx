/** Source provenance chip: colour plus text (plan 11.6). */
import type { Source } from "../contracts";
import { sourceText } from "../format";

export function SourceChip({ source, note }: { source: Source; note?: string }) {
  return (
    <span className={`source-chip source-${source}`} title={note || sourceText(source)}>
      {sourceText(source)}
    </span>
  );
}
