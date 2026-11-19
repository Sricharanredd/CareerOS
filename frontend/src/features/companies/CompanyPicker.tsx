import { Plus } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field, Input, Select } from "@/components/ui/Form";
import { useToast } from "@/components/ui/Toast";
import { errorMessage } from "@/lib/api";
import { useCompanyOptions, useCreateCompany } from "@/lib/queries";

export function CompanyPicker({
  value,
  onChange,
  error,
  disabled,
  autoFocus,
}: {
  value: string;
  onChange: (companyId: string) => void;
  error?: string;
  disabled?: boolean;
  autoFocus?: boolean;
}) {
  const options = useCompanyOptions();
  const createCompany = useCreateCompany();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");

  async function create() {
    const trimmed = name.trim();
    if (!trimmed) return;
    try {
      const company = await createCompany.mutateAsync({ name: trimmed });
      onChange(company.id);
      setAdding(false);
      setName("");
      toast.success(`Added ${company.name}.`);
    } catch (caught) {
      toast.error(errorMessage(caught));
    }
  }

  return (
    <Field label="Company" required={!disabled} error={error}>
      {adding ? (
        <div className="space-y-2">
          <Input
            autoFocus
            placeholder="Company name"
            value={name}
            maxLength={200}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void create();
              }
              if (event.key === "Escape") {
                setAdding(false);
                setName("");
              }
            }}
          />
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="primary"
              loading={createCompany.isPending}
              onClick={() => void create()}
              disabled={!name.trim()}
            >
              Add company
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setAdding(false);
                setName("");
              }}
            >
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex gap-2">
          <Select
            value={value}
            disabled={disabled || options.isLoading}
            autoFocus={autoFocus}
            onChange={(event) => onChange(event.target.value)}
          >
            <option value="">{options.isLoading ? "Loading companies…" : "Select a company"}</option>
            {options.data?.map((option) => (
              <option key={option.id} value={option.id}>
                {option.name}
                {option.archived_at ? " (archived)" : ""}
              </option>
            ))}
          </Select>
          {!disabled && (
            <Button
              variant="secondary"
              className="shrink-0"
              onClick={() => setAdding(true)}
              icon={<Plus className="h-4 w-4" />}
            >
              New
            </Button>
          )}
        </div>
      )}
    </Field>
  );
}
