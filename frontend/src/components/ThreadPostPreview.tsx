import { splitPosts, THREADS_HARD_LIMIT, THREADS_STYLE_LIMIT } from "../lib/threadSplit";

export default function ThreadPostPreview({ body }: { body: string }) {
  const posts = splitPosts(body);

  if (posts.length === 0) {
    return <p className="text-xs text-gray-400">본문이 비어 있습니다.</p>;
  }

  return (
    <div className="space-y-2">
      {posts.map((post, i) => {
        const len = post.length;
        const overHard = len > THREADS_HARD_LIMIT;
        const overStyle = len > THREADS_STYLE_LIMIT;
        return (
          <div
            key={i}
            className={`rounded-lg border p-3 ${
              overHard
                ? "border-red-400 bg-red-50"
                : overStyle
                  ? "border-amber-400 bg-amber-50"
                  : "border-gray-200 bg-white"
            }`}
          >
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="font-medium text-gray-500">
                {i + 1}/{posts.length}
              </span>
              <span
                className={
                  overHard
                    ? "font-bold text-red-600"
                    : overStyle
                      ? "font-medium text-amber-600"
                      : "text-gray-400"
                }
              >
                {len}/{THREADS_HARD_LIMIT}
                {overHard && " 초과!"}
                {!overHard && overStyle && ` (권장 ${THREADS_STYLE_LIMIT})`}
              </span>
            </div>
            <p className="whitespace-pre-wrap text-sm text-gray-800">{post}</p>
          </div>
        );
      })}
    </div>
  );
}
