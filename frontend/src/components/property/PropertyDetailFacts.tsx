import type { DetailFactGroup } from "@/lib/property-detail";

export function PropertyDetailFacts({ groups }: { groups: DetailFactGroup[] }) {
  if (!groups.length) return null;
  const compact = groups.reduce((count, group) => count + group.items.length, 0) <= 5;
  return (
    <section id="caracteristicas" className="detail-panel detail-facts scroll-mt-24">
      <h2>Características</h2>
      <div className={compact ? "detail-fact-groups is-compact" : "detail-fact-groups"}>
        {groups.map((group, index) => (
          <section key={group.title} aria-labelledby={!compact ? `facts-${index}` : undefined}>
            {!compact ? <h3 id={`facts-${index}`}>{group.title}</h3> : null}
            <dl>
              {group.items.map((item) => (
                <div key={item.label}>
                  <dt>{item.label}</dt>
                  <dd>{item.value}</dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>
    </section>
  );
}
