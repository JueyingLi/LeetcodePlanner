import ReactMarkdown from "react-markdown";

export function Markdown({ children }: { children: string }) {
  return (
    <div className="prose-custom text-sm text-[#d1d5db] leading-relaxed">
      <ReactMarkdown
        components={{
          p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
          strong: ({ children }) => <strong className="text-white font-semibold">{children}</strong>,
          em: ({ children }) => <em className="text-[#FFC800]">{children}</em>,
          ul: ({ children }) => <ul className="list-disc pl-4 mb-2 space-y-1">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal pl-4 mb-2 space-y-1">{children}</ol>,
          li: ({ children }) => <li>{children}</li>,
          code: ({ children, className }) => {
            const isBlock = className?.includes("language-");
            return isBlock ? (
              <pre className="bg-[#131F24] rounded-lg p-3 overflow-x-auto my-2">
                <code className="text-green-300 text-xs font-mono">{children}</code>
              </pre>
            ) : (
              <code className="bg-[#243640] text-[#58CC02] px-1 py-0.5 rounded text-xs font-mono">{children}</code>
            );
          },
          pre: ({ children }) => <>{children}</>,
          h1: ({ children }) => <h1 className="text-white font-bold text-base mb-2">{children}</h1>,
          h2: ({ children }) => <h2 className="text-white font-bold text-sm mb-1.5">{children}</h2>,
          h3: ({ children }) => <h3 className="text-white font-semibold text-sm mb-1">{children}</h3>,
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-[#58CC02] pl-3 my-2 text-[#9CA3AF]">{children}</blockquote>
          ),
          hr: () => <hr className="border-[#2a3f4a] my-3" />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
