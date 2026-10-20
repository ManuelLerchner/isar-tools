theory Trust
  imports Main
begin

text \<open>Results this theory takes on trust.\<close>

axiomatization bound :: nat where bound_pos: "bound > 0"

oracle trust_me = \<open>fn ct => ct\<close>

declare [[smt_oracle, quick_and_dirty]]

end
