import type { UnsubmittedHumanInputContentProps } from './type'
import ExpirationTime from './expiration-time'
import HumanInputFormRefined from './human-input-form-refined'
import Tips from './tips'

export const UnsubmittedHumanInputContent = ({
  formData,
  showEmailTip = false,
  isEmailDebugMode = false,
  showDebugModeTip = false,
  onSubmit,
}: UnsubmittedHumanInputContentProps) => {
  const { expiration_time } = formData

  return (
    <>
      {/* Form */}
      <HumanInputFormRefined
        formData={formData}
        onSubmit={onSubmit}
      />
      {/* Tips */}
      {(showEmailTip || showDebugModeTip) && (
        <Tips
          showEmailTip={showEmailTip}
          isEmailDebugMode={isEmailDebugMode}
          showDebugModeTip={showDebugModeTip}
        />
      )}
      {/* Expiration Time */}
      {typeof expiration_time === 'number' && (
        <ExpirationTime expirationTime={expiration_time * 1000} />
      )}
    </>
  )
}

