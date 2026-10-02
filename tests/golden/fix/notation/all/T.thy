theory T imports Base begin

text \<open>Every kind of short form, written out.\<close>

lemma written_out:
  "(a \<nabla> (b \<nabla> c)) = c" "(s\<langle>(f x)\<rangle>) = s" "x \<in> \<lbrakk>i\<rbrakk>" "(twice (f y)) = 0"
  sorry

text \<open>An infix passed unapplied, and an overloaded name Isabelle could not resolve here.\<close>

lemma partial: "map ((\<nabla>) a) xs = ys" "map (gamma_int) zs = ws" sorry

lemma "True" using written_out partial by simp

end
