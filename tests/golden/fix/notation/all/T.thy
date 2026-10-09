theory T imports Base begin

text \<open>Every kind of short form, written out.\<close>

lemma written_out:
  "(a \<nabla> (b \<nabla> c)) = c" "(s\<langle>f x\<rangle>) = s" "x \<in> \<lbrakk>i\<rbrakk>" "(twice (f y)) = 0"
  sorry

text \<open>An infix passed unapplied, and an overloaded name Isabelle could not resolve here.\<close>

lemma partial: "map ((\<nabla>) a) xs = ys" "map (gamma_int) zs = ws" sorry

text \<open>Brackets an argument needs only outside a slot between delimiters.\<close>

lemma brackets:
  "\<lbrakk>Suc n\<rbrakk>\<^sup>\<sharp> d = \<lbrakk>(n, m)\<rbrakk>\<^sup>\<sharp> d" "\<lbrakk>(a) + (b)\<rbrakk>\<^sup>\<sharp> d = \<lbrakk>()\<rbrakk>\<^sup>\<sharp> d" "\<lfloor>(Suc n)\<rfloor> = 0"
  sorry

lemma "True" using written_out partial brackets by simp

end
