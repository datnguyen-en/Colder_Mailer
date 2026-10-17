"use client"

import { EditorContent, useEditor, useEditorState, type Editor } from "@tiptap/react"
import StarterKit from "@tiptap/starter-kit"
import { BoldIcon, ItalicIcon, LinkIcon, ListIcon, ListOrderedIcon } from "lucide-react"
import { useEffect, useImperativeHandle, useRef, useState, useSyncExternalStore } from "react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"

export type RichTextHandle = { insertText: (text: string) => void; focus: () => void }

// Only what the backend keeps (app/richtext.py): paragraphs, bold, italic, lists, links.
const extensions = [
  StarterKit.configure({
    heading: false,
    blockquote: false,
    code: false,
    codeBlock: false,
    horizontalRule: false,
    strike: false,
    underline: false,
    link: {
      openOnClick: false,
      autolink: true,
      defaultProtocol: "https",
      protocols: ["mailto", "tel"],
    },
  }),
]

type EditorProps = {
  value: string
  onChange: (html: string) => void
  onFocus?: () => void
  /** Plain text of the content, e.g. for a word count. */
  onTextChange?: (text: string) => void
  toolbarExtra?: React.ReactNode
  ref?: React.Ref<RichTextHandle>
  minHeight?: string
  ariaLabel: string
}

const noSubscribe = () => () => {}

/** Gmail-style editor that reads and writes HTML. Browser-only: Tiptap makes random
 *  ids on creation, which Next.js doesn't allow while prerendering the page. */
export function RichTextEditor(props: EditorProps) {
  const inBrowser = useSyncExternalStore(noSubscribe, () => true, () => false)
  if (!inBrowser) {
    return (
      <div className="overflow-hidden rounded-xl border border-input bg-background">
        <div className="h-10 border-b bg-muted/60" />
        <div className={props.minHeight ?? "min-h-72"} />
      </div>
    )
  }
  return <BrowserEditor {...props} />
}

function BrowserEditor({
  value,
  onChange,
  onFocus,
  onTextChange,
  toolbarExtra,
  ref,
  minHeight = "min-h-72",
  ariaLabel,
}: EditorProps) {
  // The last HTML loaded into or produced by the editor. The server's cleaned HTML
  // differs cosmetically from the editor's, so compare against this, not getHTML().
  const lastValue = useRef(value)
  const editor = useEditor({
    extensions,
    content: value,
    immediatelyRender: false, // rendered on the client only (Next.js)
    editorProps: {
      attributes: {
        "aria-label": ariaLabel,
        class: cn("email-body rich-editor px-3.5 py-3 text-sm outline-none", minHeight),
      },
    },
    onCreate: ({ editor }) => onTextChange?.(editor.getText()),
    onUpdate: ({ editor }) => {
      lastValue.current = editor.isEmpty ? "" : editor.getHTML()
      onChange(lastValue.current)
      onTextChange?.(editor.getText())
    },
    onFocus: () => onFocus?.(),
  })

  // Load new content when the parent switches templates, without fighting the cursor while typing.
  useEffect(() => {
    if (!editor || value === lastValue.current) return
    lastValue.current = value
    editor.commands.setContent(value, { emitUpdate: false })
    onTextChange?.(editor.getText())
  }, [editor, value, onTextChange])

  useImperativeHandle(ref, () => ({
    insertText: (text) => editor?.chain().focus().insertContent(text).run(),
    focus: () => editor?.commands.focus(),
  }), [editor])

  return (
    <div className="overflow-hidden rounded-xl border border-input bg-background focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50">
      <Toolbar editor={editor} extra={toolbarExtra} />
      <EditorContent editor={editor} />
    </div>
  )
}

function Toolbar({ editor, extra }: { editor: Editor | null; extra?: React.ReactNode }) {
  const [linkOpen, setLinkOpen] = useState(false)
  const openLink = () => {
    editor?.chain().extendMarkRange("link").run()
    setLinkOpen(true)
  }
  const state = useEditorState({
    editor,
    selector: ({ editor: e }) => ({
      bold: e?.isActive("bold") ?? false,
      italic: e?.isActive("italic") ?? false,
      link: e?.isActive("link") ?? false,
      bullets: e?.isActive("bulletList") ?? false,
      numbers: e?.isActive("orderedList") ?? false,
    }),
  })

  const tools = [
    { label: "Bold", shortcut: "⌘B", icon: BoldIcon, active: state?.bold, run: () => editor?.chain().focus().toggleBold().run() },
    { label: "Italic", shortcut: "⌘I", icon: ItalicIcon, active: state?.italic, run: () => editor?.chain().focus().toggleItalic().run() },
    { label: "Link", shortcut: "⌘K", icon: LinkIcon, active: state?.link, run: openLink },
    { label: "Bulleted list", icon: ListIcon, active: state?.bullets, run: () => editor?.chain().focus().toggleBulletList().run() },
    { label: "Numbered list", icon: ListOrderedIcon, active: state?.numbers, run: () => editor?.chain().focus().toggleOrderedList().run() },
  ]

  // ⌘K / Ctrl+K opens the link dialog, like Gmail.
  useEffect(() => {
    const dom = editor?.view.dom
    if (!dom) return
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        editor.chain().extendMarkRange("link").run()
        setLinkOpen(true)
      }
    }
    dom.addEventListener("keydown", onKey)
    return () => dom.removeEventListener("keydown", onKey)
  }, [editor])

  return (
    <div className="flex flex-wrap items-center gap-0.5 border-b bg-muted/60 px-1.5 py-1">
      {tools.map(({ label, shortcut, icon: Icon, active, run }) => (
        <Button
          key={label}
          type="button"
          size="icon-sm"
          variant="ghost"
          aria-label={label}
          aria-pressed={active}
          title={shortcut ? `${label} (${shortcut})` : label}
          className={cn(active && "bg-background text-foreground shadow-xs ring-1 ring-border")}
          onMouseDown={(e) => e.preventDefault()} // keep the text selection
          onClick={run}
          disabled={!editor}
        >
          <Icon />
        </Button>
      ))}
      {extra && <div className="ml-auto flex flex-wrap items-center gap-1">{extra}</div>}
      {editor && <LinkDialog editor={editor} open={linkOpen} onOpenChange={setLinkOpen} />}
    </div>
  )
}

function LinkDialog({
  editor,
  open,
  onOpenChange,
}: {
  editor: Editor
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        {/* Mounted on open, so it starts from the current selection each time. */}
        {open && <LinkForm editor={editor} onClose={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  )
}

function normalizeHref(raw: string): string {
  const v = raw.trim()
  if (/^(https?:|mailto:|tel:)/i.test(v)) return v
  if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) return `mailto:${v}`
  if (/^\+?[\d\s().-]{7,}$/.test(v)) return `tel:${v.replace(/[^\d+]/g, "")}`
  return `https://${v}`
}

function LinkForm({ editor, onClose }: { editor: Editor; onClose: () => void }) {
  // The opener already widened the selection to the whole link under the cursor.
  const [initial] = useState(() => {
    const { from, to, empty } = editor.state.selection
    return {
      editing: editor.isActive("link"),
      hasSelection: !empty,
      url: (editor.getAttributes("link").href as string | undefined) ?? "",
      text: empty ? "" : editor.state.doc.textBetween(from, to, " "),
    }
  })
  const [url, setUrl] = useState(initial.url)
  const [text, setText] = useState(initial.text)

  function apply(e: React.FormEvent) {
    e.preventDefault()
    const href = normalizeHref(url)
    if (initial.hasSelection) {
      editor.chain().focus().extendMarkRange("link").setLink({ href }).run()
    } else {
      const label = text.trim() || url.trim()
      editor.chain().focus().insertContent({ type: "text", text: label, marks: [{ type: "link", attrs: { href } }] }).run()
    }
    onClose()
  }

  function remove() {
    editor.chain().focus().extendMarkRange("link").unsetLink().run()
    onClose()
  }

  return (
    <form onSubmit={apply} className="space-y-4">
      <DialogHeader>
        <DialogTitle>{initial.editing ? "Edit link" : "Insert link"}</DialogTitle>
      </DialogHeader>
      {!initial.hasSelection && (
        <div className="space-y-1">
          <Label htmlFor="link-text">Text to show</Label>
          <Input id="link-text" value={text} onChange={(e) => setText(e.target.value)} placeholder="won a Yale hackathon" />
        </div>
      )}
      <div className="space-y-1">
        <Label htmlFor="link-url">Web address, email, or phone</Label>
        <Input
          id="link-url"
          autoFocus
          required
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="linkedin.com/in/you"
        />
      </div>
      <DialogFooter>
        {initial.editing && <Button type="button" variant="outline" onClick={remove}>Remove link</Button>}
        <Button type="submit" disabled={!url.trim()}>{initial.editing ? "Update" : "Insert"}</Button>
      </DialogFooter>
    </form>
  )
}
