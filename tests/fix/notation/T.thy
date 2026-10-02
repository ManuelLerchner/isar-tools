theory T imports Base begin

text \<open>Every kind of short form, written out.\<close>

lemma written_out:
  "widen a (widen b c) = c" "get s (f x) = s" "x \<in> gamma_int i" "step (f y) (f y) = 0"
  sorry

text \<open>An infix passed unapplied, and an overloaded name Isabelle could not resolve here.\<close>

lemma partial: "map (widen a) xs = ys" "map (gamma_int) zs = ws" sorry

lemma "True" using written_out partial by simp

end
