theory Context imports Main begin

context
  fixes f :: "nat \<Rightarrow> nat"
begin
  definition g where "g = f"
lemma g_eq: "g = f"
  unfolding g_def ..
end

instantiation nat :: foo
begin
definition "foo = (0::nat)"
instance by standard
end

private lemma hidden: "True" by simp
end
