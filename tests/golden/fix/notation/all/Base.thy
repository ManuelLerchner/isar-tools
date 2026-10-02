theory Base imports Main begin
text \<open>Short forms of every kind.\<close>
definition widen :: "nat \<Rightarrow> nat \<Rightarrow> nat" (infixl "\<nabla>" 65) where "widen a b = b"
definition get :: "nat \<Rightarrow> nat \<Rightarrow> nat" ("_\<langle>_\<rangle>" [1000, 0] 1000) where "get s x = s"
consts gamma :: "'s \<Rightarrow> nat set" ("\<lbrakk>_\<rbrakk>")
definition gamma_int :: "int \<Rightarrow> nat set" where "gamma_int i = {}"
adhoc_overloading gamma == gamma_int
definition step :: "nat \<Rightarrow> nat \<Rightarrow> nat" where "step a b = a"
abbreviation twice where "twice x \<equiv> step x x"
end
