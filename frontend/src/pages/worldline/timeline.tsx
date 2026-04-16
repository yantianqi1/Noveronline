/**
 * Worldline vertical timeline — simple listing of canon events.
 */

interface TimelineEvent {
  title?: string;
  type?: string;
  description?: string;
  summary?: string;
}

interface WorldlineTimelineProps {
  timeline: TimelineEvent[];
}

export function WorldlineTimeline({ timeline }: WorldlineTimelineProps) {
  return (
    <article className="border border-stone-200 rounded-lg p-4 bg-white/95">
      <h2 className="text-base font-semibold text-stone-800">时间轴</h2>
      {timeline.length > 0 ? (
        <div className="mt-2.5 border-l-2 border-stone-200 pl-3 flex flex-col gap-2.5">
          {timeline.map((event, idx) => (
            <div key={idx} className="grid grid-cols-[48px_minmax(0,1fr)] gap-2.5">
              <span className="font-mono text-sm text-stone-500">
                #{idx + 1}
              </span>
              <div>
                <div className="font-bold text-sm text-stone-800">
                  {event.title || event.type || "事件"}
                </div>
                <div className="text-sm text-stone-600">
                  {event.description || event.summary || "无描述"}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-sm text-stone-500 mt-2">
          暂无时间轴数据，等世界线引擎接口接通后会自动显示。
        </div>
      )}
    </article>
  );
}
