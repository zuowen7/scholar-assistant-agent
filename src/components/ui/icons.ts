/**
 * Centralized icon barrel — re-exports the lucide icons actually used in the app.
 *
 * Add new icons here as needed. Components should import from here, never directly
 * from 'lucide-vue-next', so it's easy to swap out the icon library later.
 *
 * Default icon size is 16px, stroke 1.5 — set on each <Icon> usage via props.
 */
export {
  // Brand & navigation
  GraduationCap,
  Languages,
  FilePen as FileEdit,
  Network,

  // Actions
  Upload,
  Download,
  Save,
  Trash2,
  Plus,
  X,
  Check,
  Search,
  Settings,
  SlidersHorizontal as Sliders,
  RefreshCw,
  RotateCcw,
  RotateCw,
  Copy,
  ExternalLink,

  // Chevrons & arrows
  ChevronDown,
  ChevronUp,
  ChevronLeft,
  ChevronRight,
  ArrowRight,
  ArrowLeft,

  // Status
  CircleCheck as CheckCircle,
  CircleAlert as AlertCircle,
  TriangleAlert as AlertTriangle,
  Info,
  LoaderCircle as Loader2,
  Zap,

  // Theme & display
  Sun,
  Moon,
  Monitor,
  Image,
  Palette,
  Type,

  // Window
  Minus as WindowMinimize,
  Square as WindowMaximize,
  X as WindowClose,

  // Editor
  FileText,
  FilePlus,
  Folder,
  FolderOpen,
  FolderTree,
  PenLine,
  Eye,
  EyeOff,
  Bot,
  MessageSquare,
  Sparkles,
  BookOpen,
  Library,
  Quote,
  CodeXml as Code2,
  Table,
  Sigma,
  ListTree,

  // Mind map
  Workflow,
  GitBranch,
  CornerDownRight,

  // Drag & drop
  CloudUpload as UploadCloud,
  Maximize2,
  Minimize2,
  Pin,
  PinOff,
  GripVertical,
  MoreHorizontal,

  // Send / chat
  Send,
  Paperclip,
  Mic,

  // Toggle / panel
  PanelLeft,
  PanelRight,
  PanelLeftClose,
  PanelRightClose,
  LayoutGrid,
} from 'lucide-vue-next'
