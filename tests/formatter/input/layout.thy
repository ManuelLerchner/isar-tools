(* A comment before the header
   keeps its layout. *)
theory Layout imports Main begin   



text \<open>Prose is never
      reflowed.\<close>
lemma multi: "x = y \<Longrightarrow>
              y = x"
by simp
    (* an indented comment stays *)
lemma bracket: "P"
  apply (rule_tac x = 1
    and y = 2 in exI)
  apply (rule foo[where x = 1
                   and y = 2])
  done
lemma right_aligned:
  assumes a: "A"
      and b: "B"
  shows "A"
  using a by simp
lemma for_clause: "P x" if "Q x"
for x
using that by simp



end
