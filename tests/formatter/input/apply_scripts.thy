theory Apply_Scripts imports Main begin

lemma conj: "A \<and> B"
apply (rule conjI)
 apply simp
apply (simp add: foo
  bar)
done

lemma sub: "A \<and> B"
  apply (rule conjI)
   subgoal by simp
  subgoal
  apply simp
  done
  done

lemma abandoned: "False"
oops

end
