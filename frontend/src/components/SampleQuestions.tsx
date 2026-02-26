interface SampleQuestionsProps {
  onSelect: (question: string) => void
  disabled?: boolean
}

const SAMPLE_QUESTIONS = [
  'What is total revenue by region for 2024?',
  'Compare Q3 vs Q4 2024 sales by category',
  'Show top 5 countries by profit margin',
]

export function SampleQuestions({ onSelect, disabled }: SampleQuestionsProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {SAMPLE_QUESTIONS.map((question, idx) => (
        <button
          key={idx}
          onClick={() => onSelect(question)}
          disabled={disabled}
          className="
            px-3 py-1.5 text-sm rounded-full border
            border-blue-300 bg-blue-50 text-blue-700
            hover:bg-blue-100 hover:border-blue-400
            disabled:opacity-50 disabled:cursor-not-allowed
            transition-colors duration-150 whitespace-nowrap
          "
        >
          {question}
        </button>
      ))}
    </div>
  )
}
