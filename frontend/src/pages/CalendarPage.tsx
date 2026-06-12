import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAutoSchedule, useCalendar, useContents, useInvalidate } from "../api/hooks";
import { api } from "../api/client";
import type { AutoScheduleItem, CalendarItem } from "../api/types";
import StatusBadge from "../components/StatusBadge";
import {
  addDays,
  mondayOf,
  PUBLISH_SLOTS,
  toDateKey,
  WEEKDAYS_KR,
} from "../lib/dates";

function SlotPicker({
  date,
  time,
  onClose,
}: {
  date: string;
  time: string;
  onClose: () => void;
}) {
  const { data } = useContents({ status: "리뷰완료" });
  const [error, setError] = useState("");
  const invalidate = useInvalidate();

  const assign = async (id: number) => {
    setError("");
    try {
      await api.post(`/contents/${id}/schedule`, {
        scheduled_at: `${date}T${time}:00`,
      });
      invalidate();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="mb-3 text-sm font-bold">
          {date} {time} 슬롯에 배정할 콘텐츠
        </h3>
        {error && <p className="mb-2 text-xs text-red-600">{error}</p>}
        <div className="max-h-72 space-y-1.5 overflow-y-auto">
          {(data?.items ?? []).length === 0 && (
            <p className="py-4 text-center text-xs text-gray-400">
              리뷰완료 상태의 콘텐츠가 없습니다.
            </p>
          )}
          {(data?.items ?? []).map((c) => (
            <button
              key={c.id}
              onClick={() => assign(c.id)}
              className="block w-full rounded-lg border border-gray-200 p-2.5 text-left text-sm hover:border-gray-500"
            >
              <span className="mr-2 rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">
                {c.category}
              </span>
              {c.title}
            </button>
          ))}
        </div>
        <button
          onClick={onClose}
          className="mt-3 w-full rounded-lg bg-gray-100 py-2 text-sm text-gray-600 hover:bg-gray-200"
        >
          닫기
        </button>
      </div>
    </div>
  );
}

function AutoScheduleDialog({ onClose }: { onClose: () => void }) {
  const autoSchedule = useAutoSchedule();
  const [preview, setPreview] = useState<AutoScheduleItem[] | null>(null);
  const requested = useRef(false);

  useEffect(() => {
    if (requested.current) return;
    requested.current = true;
    autoSchedule
      .mutateAsync({ preview: true })
      .then((r) => setPreview(r.assignments));
  }, [autoSchedule]);

  const commit = async () => {
    await autoSchedule.mutateAsync({ preview: false });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-xl bg-white p-5 shadow-xl">
        <h3 className="mb-3 text-sm font-bold">자동 배정 미리보기</h3>
        {preview === null ? (
          <p className="py-4 text-center text-sm text-gray-500">계산 중...</p>
        ) : preview.length === 0 ? (
          <p className="py-4 text-center text-sm text-gray-500">
            배정할 리뷰완료 스레드가 없거나 슬롯이 모두 찼습니다.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-gray-500">
                <th className="py-1.5">콘텐츠</th>
                <th>카테고리</th>
                <th>발행시간</th>
              </tr>
            </thead>
            <tbody>
              {preview.map((a) => (
                <tr key={a.content_id} className="border-b border-gray-100">
                  <td className="max-w-48 truncate py-1.5">{a.title}</td>
                  <td>{a.category}</td>
                  <td className="text-xs">
                    {new Date(a.scheduled_at).toLocaleString("ko-KR", {
                      month: "numeric",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
          >
            취소
          </button>
          <button
            onClick={commit}
            disabled={!preview || preview.length === 0 || autoSchedule.isPending}
            className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-40"
          >
            배정 확정
          </button>
        </div>
      </div>
    </div>
  );
}

export default function CalendarPage() {
  const [weekStart, setWeekStart] = useState(() => mondayOf(new Date()));
  const [pickerSlot, setPickerSlot] = useState<{ date: string; time: string } | null>(null);
  const [showAuto, setShowAuto] = useState(false);

  const start = toDateKey(weekStart);
  const end = toDateKey(addDays(weekStart, 6));
  const { data } = useCalendar(start, end);

  const itemsByDateTime = new Map<string, CalendarItem[]>();
  const offSlotItems: { date: string; item: CalendarItem }[] = [];
  for (const day of data?.days ?? []) {
    for (const item of day.items) {
      if (PUBLISH_SLOTS.includes(item.time)) {
        const key = `${day.date}|${item.time}`;
        itemsByDateTime.set(key, [...(itemsByDateTime.get(key) ?? []), item]);
      } else {
        offSlotItems.push({ date: day.date, item });
      }
    }
  }

  const today = toDateKey(new Date());

  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <button
          onClick={() => setWeekStart(addDays(weekStart, -7))}
          className="rounded-lg bg-white px-3 py-1.5 text-sm shadow-sm hover:bg-gray-100"
        >
          ← 이전 주
        </button>
        <span className="text-sm font-bold text-gray-700">
          {start} ~ {end}
        </span>
        <button
          onClick={() => setWeekStart(addDays(weekStart, 7))}
          className="rounded-lg bg-white px-3 py-1.5 text-sm shadow-sm hover:bg-gray-100"
        >
          다음 주 →
        </button>
        <button
          onClick={() => setWeekStart(mondayOf(new Date()))}
          className="rounded-lg bg-white px-3 py-1.5 text-sm shadow-sm hover:bg-gray-100"
        >
          오늘
        </button>
        <button
          onClick={() => setShowAuto(true)}
          className="ml-auto rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700"
        >
          자동 배정
        </button>
      </div>

      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
        <table className="w-full table-fixed">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="w-16 p-2 text-xs text-gray-400">슬롯</th>
              {Array.from({ length: 7 }, (_, i) => {
                const d = addDays(weekStart, i);
                const key = toDateKey(d);
                const isToday = key === today;
                return (
                  <th
                    key={key}
                    className={`p-2 text-xs font-medium ${isToday ? "bg-blue-50 text-blue-700" : "text-gray-600"}`}
                  >
                    {WEEKDAYS_KR[d.getDay()]} {d.getMonth() + 1}/{d.getDate()}
                    {isToday && " (오늘)"}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {PUBLISH_SLOTS.map((slot) => (
              <tr key={slot} className="border-b border-gray-100">
                <td className="p-2 text-center text-xs font-medium text-gray-500">
                  {slot}
                </td>
                {Array.from({ length: 7 }, (_, i) => {
                  const dateKey = toDateKey(addDays(weekStart, i));
                  const items = itemsByDateTime.get(`${dateKey}|${slot}`) ?? [];
                  return (
                    <td key={dateKey} className="h-20 p-1.5 align-top">
                      {items.length === 0 ? (
                        <button
                          onClick={() => setPickerSlot({ date: dateKey, time: slot })}
                          className="h-full w-full rounded-lg border border-dashed border-gray-200 text-xs text-gray-300 hover:border-gray-400 hover:text-gray-500"
                        >
                          + 배정
                        </button>
                      ) : (
                        items.map((item) => (
                          <Link
                            key={item.content_id}
                            to={`/contents/${item.content_id}`}
                            className="block rounded-lg border border-gray-200 bg-gray-50 p-1.5 hover:border-gray-400"
                          >
                            <div className="mb-0.5 flex items-center gap-1">
                              <span className="rounded bg-gray-200 px-1 text-[10px] text-gray-600">
                                {item.category}
                              </span>
                              <StatusBadge status={item.status} />
                            </div>
                            <p className="line-clamp-2 text-xs text-gray-800">
                              {item.title}
                            </p>
                          </Link>
                        ))
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {offSlotItems.length > 0 && (
        <div className="mt-4">
          <h3 className="mb-2 text-sm font-bold text-gray-600">
            슬롯 외 시간 예약
          </h3>
          <div className="space-y-1.5">
            {offSlotItems.map(({ date, item }) => (
              <Link
                key={item.content_id}
                to={`/contents/${item.content_id}`}
                className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white p-2 text-sm hover:border-gray-400"
              >
                <span className="text-xs text-gray-500">
                  {date} {item.time}
                </span>
                <StatusBadge status={item.status} />
                <span className="truncate">{item.title}</span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {pickerSlot && (
        <SlotPicker
          date={pickerSlot.date}
          time={pickerSlot.time}
          onClose={() => setPickerSlot(null)}
        />
      )}
      {showAuto && <AutoScheduleDialog onClose={() => setShowAuto(false)} />}
    </div>
  );
}
