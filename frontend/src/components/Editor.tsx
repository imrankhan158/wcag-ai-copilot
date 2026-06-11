import CodeMirror from "@uiw/react-codemirror";
import { html } from "@codemirror/lang-html";
import { vscodeDark } from "@uiw/codemirror-theme-vscode";

interface EditorProps {
  value: string;
  onChange: (val: string) => void;
  placeholder?: string;
}

export function Editor({ value, onChange, placeholder }: EditorProps) {
  return (
    <div className="flex-1 flex flex-col min-h-[250px] border border-slate-800 rounded-xl overflow-hidden bg-[#1e1e1e]/60 shadow-2xl focus-within:border-blue-500/40 focus-within:ring-1 focus-within:ring-blue-500/15 transition-all">
      <div className="bg-[#1e1e1e]/90 px-4 py-2 border-b border-slate-800/80 flex items-center justify-between text-xs text-slate-400 font-mono">
        <span>source_code_input.html</span>
        <span className="text-[10px] text-blue-400 font-semibold tracking-wider uppercase">HTML/JSX Mode</span>
      </div>
      <div className="flex-1 overflow-auto">
        <CodeMirror
          value={value}
          height="100%"
          minHeight="250px"
          theme={vscodeDark}
          extensions={[html()]}
          onChange={(val) => onChange(val)}
          placeholder={placeholder}
          className="text-sm font-mono h-full"
          basicSetup={{
            lineNumbers: true,
            foldGutter: true,
            highlightActiveLine: false,
          }}
        />
      </div>
    </div>
  );
}
